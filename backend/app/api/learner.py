"""Mini App API for learners. Every request is authenticated with Telegram initData."""
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import SessionLocal, get_session
from ..grading import AIError, gemini_grade, self_check_score
from ..models import (Attempt, AttemptState, Course, KeyPoint, PaymentRequest, PaymentStatus, Plan,
                      Question, StoredFile, Topic, User, UserStatus)
from ..config import get_settings
from ..security import current_user
from ..services import (AUDIO_TYPES, IMAGE_TYPES, MAX_AUDIO, MAX_IMAGE, active_subscription, can_answer,
                        effective_status, file_id, file_ref, free_question_ids, get_settings_map,
                        new_payment_code, now_utc, round_half, store_upload, subscription_covers,
                        sync_user_status)
from .. import telegram

log = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["learner"])


def not_blocked(user: User) -> User:
    if user.status == UserStatus.blocked:
        raise HTTPException(403, "blocked")
    return user


# ---------------------------------------------------------------- profile

@router.get("/me")
async def me(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    s = await get_settings_map(session)
    status = await effective_status(session, user)
    sub = await active_subscription(session, user.id)
    plan = await session.get(Plan, sub.plan_id) if sub and sub.plan_id else None
    pending = (await session.execute(select(PaymentRequest).where(
        PaymentRequest.user_id == user.id).order_by(PaymentRequest.id.desc()).limit(1))).scalar_one_or_none()
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "phone": user.phone,
        "ui_language": user.ui_language,
        "course_id": user.course_id,
        "status": status.value,
        "subscription": {"ends_at": sub.ends_at, "plan": plan.name if plan else None} if sub else None,
        "last_payment": {"status": pending.status.value, "reject_reason": pending.reject_reason,
                         "code": pending.payment_code} if pending else None,
        "is_admin": user.telegram_id in get_settings().admin_ids,
        "support_contact": s["support_contact"],
        "grading_mode": s["grading_mode"] if (s["grading_mode"] != "ai" or s["gemini_api_key"]) else "self",
        "free_questions": s["free_questions"],
        "max_answer_seconds": s["max_answer_seconds"],
    }


class MePatch(BaseModel):
    ui_language: str | None = None
    course_id: int | None = None


@router.patch("/me")
async def update_me(body: MePatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if body.ui_language is not None:
        if body.ui_language not in ("uz", "ru", "en"):
            raise HTTPException(400, "language must be uz, ru or en")
        user.ui_language = body.ui_language
    if body.course_id is not None:
        course = await session.get(Course, body.course_id)
        if not course or not course.is_published:
            raise HTTPException(404, "course not found")
        user.course_id = course.id
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- content

@router.get("/courses")
async def list_courses(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    counts = dict((await session.execute(
        select(Question.course_id, func.count()).where(Question.is_active.is_(True))
        .group_by(Question.course_id))).all())
    rows = (await session.execute(select(Course).where(Course.is_published.is_(True))
                                  .order_by(Course.id))).scalars()
    return [{"id": c.id, "name": c.name, "description": c.description, "cover": c.cover,
             "questions": counts.get(c.id, 0)} for c in rows]


@router.get("/courses/{course_id}/questions")
async def course_questions(course_id: int, user: User = Depends(current_user),
                           session: AsyncSession = Depends(get_session)):
    not_blocked(user)
    course = await session.get(Course, course_id)
    if not course or not course.is_published:
        raise HTTPException(404, "course not found")
    s = await get_settings_map(session)
    sub = await active_subscription(session, user.id)
    full = await subscription_covers(session, sub, course_id)
    free = await free_question_ids(session, course_id, int(s["free_questions"]))
    topics = (await session.execute(select(Topic).where(Topic.course_id == course_id)
                                    .order_by(Topic.order, Topic.id))).scalars().all()
    qs = (await session.execute(select(Question).where(
        Question.course_id == course_id, Question.is_active.is_(True))
        .order_by(Question.number, Question.id))).scalars().all()
    stats = {qid: (best, n) for qid, best, n in (await session.execute(
        select(Attempt.question_id, func.max(func.coalesce(Attempt.manual_score, Attempt.score)), func.count())
        .where(Attempt.user_id == user.id, Attempt.state == AttemptState.graded)
        .group_by(Attempt.question_id))).all()}
    return {
        "course": {"id": course.id, "name": course.name},
        "full_access": full,
        "topics": [{"id": t.id, "name": t.name} for t in topics],
        "questions": [{
            "id": q.id, "number": q.number, "text": q.text, "topic_id": q.topic_id,
            "locked": not (full or q.id in free), "free": q.id in free,
            "best_score": stats.get(q.id, (None, 0))[0], "attempts": stats.get(q.id, (None, 0))[1],
        } for q in qs],
    }


@router.get("/questions/{question_id}")
async def get_question(question_id: int, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    not_blocked(user)
    q = await session.get(Question, question_id)
    course = await session.get(Course, q.course_id) if q else None
    if not q or not q.is_active or not course or not course.is_published:
        raise HTTPException(404, "question not found")
    allowed = await can_answer(session, user, q)
    topic = await session.get(Topic, q.topic_id) if q.topic_id else None
    return {"id": q.id, "number": q.number, "course_id": q.course_id, "text": q.text,
            "topic": topic.name if topic else None, "locked": not allowed,
            "question_audio": file_id(q.question_audio) if allowed else None}


# ---------------------------------------------------------------- attempts

async def attempt_detail(session: AsyncSession, a: Attempt) -> dict:
    q = (await session.execute(select(Question).options(selectinload(Question.key_points))
                               .where(Question.id == a.question_id))).scalar_one()
    return {
        "id": a.id, "state": a.state.value, "created_at": a.created_at,
        "question": {"id": q.id, "number": q.number, "text": q.text, "course_id": q.course_id},
        "model_answer": q.model_answer, "explanation": q.explanation,
        "model_audio": file_id(q.answer_audio),
        "key_points": [{"id": k.id, "text": k.text, "weight": k.weight}
                       for k in sorted(q.key_points, key=lambda k: k.id)],
        "audio": file_id(a.audio_file),
        "transcript": a.transcript,
        "score": a.manual_score if a.manual_score is not None else a.score,
        "auto_score": a.score, "manual_score": a.manual_score,
        "covered": a.covered_points or [], "wrong": a.wrong_statements or [],
        "comment": a.comment, "what_to_add": a.what_to_add,
        "graded_by": a.mode,
    }


async def run_ai_grading(attempt_id: int) -> None:
    async with SessionLocal() as session:
        a = await session.get(Attempt, attempt_id)
        if a is None:
            return
        s = await get_settings_map(session)
        q = (await session.execute(select(Question).options(selectinload(Question.key_points))
                                   .where(Question.id == a.question_id))).scalar_one()
        audio = await session.get(StoredFile, file_id(a.audio_file)) if file_id(a.audio_file) else None
        try:
            if audio is None:
                raise AIError("no audio")
            res = await gemini_grade(
                api_key=s["gemini_api_key"], model=s["gemini_model"], audio=audio.data,
                content_type=audio.content_type, question=q.text, model_answer=q.model_answer,
                key_points=[(k.id, k.weight, k.text) for k in q.key_points], rules=s["ai_rules"])
        except AIError as exc:
            log.warning("AI grading failed for attempt %s: %s", attempt_id, exc)
            a.state = AttemptState.failed_retry
            a.comment = None
            await session.commit()
            return
        a.transcript = res["transcript"]
        a.covered_points = res["covered"]
        a.missed_points = [k.id for k in q.key_points if k.id not in res["covered"]]
        a.wrong_statements = res["wrong"]
        a.score = res["score"]
        a.comment = res["comment"]
        a.what_to_add = res["what_to_add"]
        a.ai_cost = float(res["tokens"])  # token count; priced in the dashboard
        a.mode = "ai"
        a.state = AttemptState.graded
        await session.commit()


@router.post("/attempts")
async def create_attempt(
    background: BackgroundTasks,
    question_id: int = Form(...),
    audio: UploadFile = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    not_blocked(user)
    q = await session.get(Question, question_id)
    if not q or not q.is_active:
        raise HTTPException(404, "question not found")
    if not await can_answer(session, user, q):
        raise HTTPException(402, "subscription required")
    s = await get_settings_map(session)
    since = now_utc() - timedelta(days=1)
    today = (await session.execute(select(func.count()).select_from(Attempt).where(
        Attempt.user_id == user.id, Attempt.created_at > since))).scalar_one()
    if today >= int(s["daily_cap"]):
        raise HTTPException(429, "daily limit reached")
    f = await store_upload(session, audio, "answer_audio", user.id, AUDIO_TYPES, MAX_AUDIO)
    if f.size < 2000:
        raise HTTPException(400, "recording too short")
    use_ai = s["grading_mode"] == "ai" and bool(s["gemini_api_key"])
    a = Attempt(user_id=user.id, question_id=q.id, mode="ai" if use_ai else "self",
                audio_file=file_ref(f), state=AttemptState.grading if use_ai else AttemptState.recorded)
    session.add(a)
    await session.commit()
    await session.refresh(a)
    if use_ai:
        background.add_task(run_ai_grading, a.id)
    return await attempt_detail(session, a)


async def own_attempt(session: AsyncSession, attempt_id: int, user: User) -> Attempt:
    a = await session.get(Attempt, attempt_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "attempt not found")
    return a


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: int, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    return await attempt_detail(session, await own_attempt(session, attempt_id, user))


class SelfGrade(BaseModel):
    covered: list[int] = []
    score: float | None = None  # only used when the question has no key points


@router.post("/attempts/{attempt_id}/self-grade")
async def self_grade(attempt_id: int, body: SelfGrade, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    a = await own_attempt(session, attempt_id, user)
    if a.state not in (AttemptState.recorded, AttemptState.failed_retry, AttemptState.graded) or a.mode == "ai" \
            and a.state == AttemptState.graded:
        raise HTTPException(409, "attempt cannot be self-graded now")
    kps = (await session.execute(select(KeyPoint).where(KeyPoint.question_id == a.question_id))).scalars().all()
    if kps:
        ids = {k.id for k in kps}
        covered = sorted(set(body.covered) & ids)
        a.score = self_check_score([(k.id, k.weight) for k in kps], set(covered))
        a.covered_points = covered
        a.missed_points = sorted(ids - set(covered))
    else:
        if body.score is None:
            raise HTTPException(400, "score required")
        a.score = round_half(body.score)
        a.covered_points, a.missed_points = [], []
    a.mode = "self"
    a.state = AttemptState.graded
    await session.commit()
    return await attempt_detail(session, a)


@router.get("/attempts")
async def my_attempts(limit: int = 50, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Attempt, Question.number, Question.text).join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user.id).order_by(Attempt.id.desc()).limit(min(max(limit, 1), 200)))).all()
    graded = [a for a, _, _ in rows if a.state == AttemptState.graded]
    avg = round(sum((a.manual_score if a.manual_score is not None else a.score) or 0 for a in graded)
                / len(graded), 2) if graded else None
    total = (await session.execute(select(func.count(func.distinct(Attempt.question_id))).where(
        Attempt.user_id == user.id, Attempt.state == AttemptState.graded))).scalar_one()
    return {
        "stats": {"answered_questions": total, "average": avg, "attempts": len(rows)},
        "items": [{"id": a.id, "state": a.state.value, "created_at": a.created_at, "question_id": a.question_id,
                   "number": n, "text": t,
                   "score": a.manual_score if a.manual_score is not None else a.score} for a, n, t in rows],
    }


# ---------------------------------------------------------------- files

@router.get("/files/{fid}")
async def learner_file(fid: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from fastapi import Response
    f = await session.get(StoredFile, fid)
    if not f:
        raise HTTPException(404, "file not found")
    if f.owner_user_id != user.id:
        if f.kind not in ("question_audio", "model_audio"):
            raise HTTPException(404, "file not found")
        ref = file_ref(f)
        q = (await session.execute(select(Question).where(
            (Question.question_audio == ref) | (Question.answer_audio == ref)).limit(1))).scalar_one_or_none()
        if not q or not await can_answer(session, user, q):
            raise HTTPException(404, "file not found")
    return Response(f.data, media_type=f.content_type, headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- plans and payments

@router.get("/plans")
async def list_plans(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    plans = (await session.execute(select(Plan).options(selectinload(Plan.courses))
                                   .where(Plan.is_active.is_(True)).order_by(Plan.price_uzs))).scalars()
    return [{"id": p.id, "name": p.name, "days": p.days, "price_uzs": p.price_uzs,
             "courses": [c.name for c in p.courses]} for p in plans]


@router.get("/payment-info")
async def payment_info(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    s = await get_settings_map(session)
    return {"card_number": s["card_number"], "card_holder": s["card_holder"], "note": s["payment_note"]}


@router.post("/payments")
async def create_payment(
    background: BackgroundTasks,
    plan_id: int = Form(...),
    receipt: UploadFile = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    not_blocked(user)
    plan = await session.get(Plan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(404, "plan not found")
    open_req = (await session.execute(select(PaymentRequest.id).where(
        PaymentRequest.user_id == user.id, PaymentRequest.status == PaymentStatus.pending))).first()
    if open_req:
        raise HTTPException(409, "you already have a request waiting for review")
    f = await store_upload(session, receipt, "receipt", user.id, IMAGE_TYPES + ("application/pdf",), MAX_IMAGE)
    req = PaymentRequest(user_id=user.id, plan_id=plan.id, amount=plan.price_uzs,
                         payment_code=await new_payment_code(session), receipt_image=file_ref(f))
    session.add(req)
    await session.flush()
    await sync_user_status(session, user)
    await session.commit()

    async def notify(req_id: int):
        async with SessionLocal() as s2:
            r = await s2.get(PaymentRequest, req_id)
            if r:
                await telegram.notify_admins_payment(s2, r)

    background.add_task(notify, req.id)
    return {"id": req.id, "code": req.payment_code, "status": req.status.value}


@router.get("/payments")
async def my_payments(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(PaymentRequest, Plan.name).join(Plan, Plan.id == PaymentRequest.plan_id)
        .where(PaymentRequest.user_id == user.id).order_by(PaymentRequest.id.desc()).limit(20))).all()
    return [{"id": r.id, "plan": name, "amount": r.amount, "code": r.payment_code, "status": r.status.value,
             "reject_reason": r.reject_reason, "created_at": r.created_at} for r, name in rows]
