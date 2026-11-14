"""Admin AI voice: generate question / model-answer audio with one click, or for every question that has none."""
import asyncio
import itertools
import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import tts
from ..db import SessionLocal, get_session
from ..models import Course, Question, StoredFile, User
from ..security import admin_user
from ..services import audit, file_id, file_ref, get_settings_map

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/admin", tags=["admin"])

Kind = Literal["question", "answer"]
Lang = Literal["uz", "ru"]
PAUSE = 0.15  # be gentle with Azure's rate limit

# Batch jobs live in memory (one server). If the server restarts mid-job, run it again: it only fills what is missing.
JOBS: dict[int, dict] = {}
_job_ids = itertools.count(1)


def voice_config(s: dict, lang: str) -> dict:
    return {"key": s["azure_tts_key"], "region": s["azure_tts_region"].strip().lower(),
            "voice": (s["tts_voice_uz"] if lang == "uz" else s["tts_voice_ru"]).strip()}


def text_of(q: Question, kind: str) -> str:
    return q.text if kind == "question" else q.model_answer


async def generate_for(session: AsyncSession, q: Question, kind: str, cfg: dict) -> int:
    """Synthesize one clip, store it and attach it to the question (replacing any old clip). Returns the file id."""
    audio = await tts.synthesize(text_of(q, kind), **cfg)
    f = StoredFile(owner_user_id=None, kind="question_audio" if kind == "question" else "model_audio",
                   content_type="audio/mpeg", size=len(audio), data=audio)
    session.add(f)
    await session.flush()
    old = file_id(q.question_audio if kind == "question" else q.answer_audio)
    if kind == "question":
        q.question_audio = file_ref(f)
    else:
        q.answer_audio = file_ref(f)
    if old:
        await session.execute(delete(StoredFile).where(StoredFile.id == old))
    return f.id


class OneIn(BaseModel):
    kind: Kind
    lang: Lang = "uz"
    overwrite: bool = False


class BulkIn(BaseModel):
    lang: Lang = "uz"
    kinds: list[Kind] = ["question", "answer"]


@router.get("/tts/status")
async def status(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    s = await get_settings_map(session)
    return {"configured": bool(s["azure_tts_key"] and s["azure_tts_region"]),
            "voices": {"uz": s["tts_voice_uz"], "ru": s["tts_voice_ru"]}}


@router.post("/questions/{question_id}/tts")
async def generate_one(question_id: int, body: OneIn, admin: User = Depends(admin_user),
                       session: AsyncSession = Depends(get_session)):
    q = await session.get(Question, question_id)
    if q is None:
        raise HTTPException(404, "question not found")
    have = q.question_audio if body.kind == "question" else q.answer_audio
    if have and not body.overwrite:
        raise HTTPException(409, "this question already has audio (a teacher's recording has priority)")
    try:
        fid = await generate_for(session, q, body.kind, voice_config(await get_settings_map(session), body.lang))
    except tts.TTSError as exc:
        raise HTTPException(400, str(exc))
    audit(session, admin.telegram_id, f"question.tts.{body.kind}", f"question:{q.id}")
    await session.commit()
    return {"ok": True, "file": fid}


async def run_job(job_id: int, course_id: int, lang: str, kinds: list[str]) -> None:
    job = JOBS[job_id]
    try:
        async with SessionLocal() as session:
            cfg = voice_config(await get_settings_map(session), lang)
            ids = list((await session.execute(select(Question.id).where(
                Question.course_id == course_id, Question.is_active.is_(True)).order_by(Question.number))).scalars())
        for qid in ids:
            for kind in kinds:
                if job["abort"]:
                    return
                async with SessionLocal() as session:
                    q = await session.get(Question, qid)
                    if q is None or (q.question_audio if kind == "question" else q.answer_audio):
                        continue  # never overwrite: a teacher's recording has priority
                    if not text_of(q, kind).strip():
                        job["skipped"] += 1
                        continue
                    try:
                        await generate_for(session, q, kind, cfg)
                        await session.commit()
                        job["done"] += 1
                    except tts.TTSError as exc:
                        await session.rollback()
                        job["failed"] += 1
                        job["last_error"] = str(exc)
                        if exc.fatal:
                            job["abort"] = True
                            return
                await asyncio.sleep(PAUSE)
    except Exception as exc:  # never leave a job "running" forever
        log.exception("voice job %s crashed", job_id)
        job["last_error"] = f"unexpected error: {type(exc).__name__}"
    finally:
        job["running"] = False


@router.post("/courses/{course_id}/tts-missing")
async def generate_missing(course_id: int, body: BulkIn, background: BackgroundTasks,
                           admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    if await session.get(Course, course_id) is None:
        raise HTTPException(404, "course not found")
    s = await get_settings_map(session)
    if not (s["azure_tts_key"] and s["azure_tts_region"]):
        raise HTTPException(400, "set the Azure Speech key and region in Settings first")
    if any(j["running"] and j["course_id"] == course_id for j in JOBS.values()):
        raise HTTPException(409, "a voice job is already running for this course")
    qs = (await session.execute(select(Question).where(
        Question.course_id == course_id, Question.is_active.is_(True)))).scalars().all()
    todo = sum(1 for q in qs for k in body.kinds
               if not (q.question_audio if k == "question" else q.answer_audio) and text_of(q, k).strip())
    job_id = next(_job_ids)
    JOBS[job_id] = {"course_id": course_id, "total": todo, "done": 0, "failed": 0, "skipped": 0,
                    "running": todo > 0, "abort": False, "last_error": None}
    audit(session, admin.telegram_id, "course.tts_missing", f"course:{course_id}", new={"lang": body.lang, "clips": todo})
    await session.commit()
    if todo:
        background.add_task(run_job, job_id, course_id, body.lang, list(body.kinds))
    return {"job_id": job_id, **{k: v for k, v in JOBS[job_id].items() if k != "abort"}}


@router.get("/tts/jobs/{job_id}")
async def job_status(job_id: int, _: User = Depends(admin_user)):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found (the server may have restarted: start it again, it only fills what is missing)")
    return {"job_id": job_id, **{k: v for k, v in job.items() if k != "abort"}}
