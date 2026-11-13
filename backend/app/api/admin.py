"""Admin panel API. Browser sign-in with Telegram Login; only IDs in ADMIN_TELEGRAM_IDS."""
import io
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import telegram
from ..config import Settings, get_settings
from ..db import get_session
from ..models import (Attempt, AttemptState, AuditLog, Course, KeyPoint, PaymentRequest, PaymentStatus, Plan,
                      Question, StoredFile, Subscription, SubscriptionSource, SubscriptionStatus, Topic, User,
                      UserStatus)
from ..security import InitDataError, admin_user, make_admin_session, upsert_user, verify_login_widget
from ..services import (AUDIO_TYPES, DEFAULT_SETTINGS, SECRET_SETTINGS, MAX_AUDIO, active_subscription,
                        approve_payment, audit, effective_status, file_id, file_ref, get_settings_map,
                        grant_days, now_utc, put_settings, reject_payment, round_half, store_upload,
                        sync_user_status)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------- auth

class TelegramLogin(BaseModel):
    """Fields sent by the Telegram Login Widget; any extra field is part of the signature."""
    model_config = ConfigDict(extra="allow")
    id: int
    auth_date: int
    hash: str


@router.post("/login")
async def admin_login(body: TelegramLogin, session: AsyncSession = Depends(get_session),
                      settings: Settings = Depends(get_settings)):
    """Browser sign-in: verify the Telegram Login Widget data and issue an admin session token."""
    if not settings.bot_token:
        raise HTTPException(503, "server misconfigured: BOT_TOKEN not set")
    try:
        fields = verify_login_widget(body.model_dump(), settings.bot_token, settings.init_data_max_age_seconds)
    except InitDataError as exc:
        raise HTTPException(401, f"invalid login: {exc}")
    tg_id = int(fields["id"])
    if tg_id not in settings.admin_ids:
        raise HTTPException(403, "admin only")
    full_name = " ".join(p for p in (fields.get("first_name"), fields.get("last_name")) if p) or None
    await upsert_user(session, tg_id, full_name)
    token, expires = make_admin_session(tg_id, settings.bot_token, settings.admin_session_ttl_seconds)
    return {"token": token, "expires_at": expires}


@router.get("/me")
async def admin_me(user: User = Depends(admin_user)):
    """200 only for Telegram IDs on the admin list; the admin panel gates on this."""
    return {"telegram_id": user.telegram_id, "full_name": user.full_name, "is_admin": True}


# ---------------------------------------------------------------- dashboard

@router.get("/dashboard")
async def dashboard(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    now = now_utc()
    day = now - timedelta(days=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def count(stmt):
        return (await session.execute(stmt)).scalar_one()

    return {
        "users": await count(select(func.count()).select_from(User)),
        "new_users_today": await count(select(func.count()).select_from(User).where(User.created_at > day)),
        "active_subscribers": await count(select(func.count(func.distinct(Subscription.user_id))).where(
            Subscription.status == SubscriptionStatus.active, Subscription.ends_at > now)),
        "pending_payments": await count(select(func.count()).select_from(PaymentRequest).where(
            PaymentRequest.status == PaymentStatus.pending)),
        "answers_today": await count(select(func.count()).select_from(Attempt).where(Attempt.created_at > day)),
        "answers_total": await count(select(func.count()).select_from(Attempt)),
        "revenue_month": await count(select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.status == PaymentStatus.approved, PaymentRequest.reviewed_at >= month_start)),
        "questions": await count(select(func.count()).select_from(Question).where(Question.is_active.is_(True))),
        "ai_tokens_today": await count(select(func.coalesce(func.sum(Attempt.ai_cost), 0)).where(
            Attempt.created_at > day)),
    }


# ---------------------------------------------------------------- payments

@router.get("/payments")
async def list_payments(status: str | None = "pending", _: User = Depends(admin_user),
                        session: AsyncSession = Depends(get_session)):
    stmt = (select(PaymentRequest, User, Plan.name).join(User, User.id == PaymentRequest.user_id)
            .join(Plan, Plan.id == PaymentRequest.plan_id).order_by(PaymentRequest.id.desc()).limit(200))
    if status and status != "all":
        try:
            stmt = stmt.where(PaymentRequest.status == PaymentStatus(status))
        except ValueError:
            raise HTTPException(400, "bad status")
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "code": r.payment_code, "amount": r.amount, "status": r.status.value,
             "plan": plan, "receipt": file_id(r.receipt_image), "reject_reason": r.reject_reason,
             "created_at": r.created_at, "reviewed_at": r.reviewed_at,
             "user": {"id": u.id, "name": u.full_name, "phone": u.phone, "telegram_id": u.telegram_id}}
            for r, u, plan in rows]


@router.post("/payments/{req_id}/approve")
async def approve(req_id: int, background: BackgroundTasks, admin: User = Depends(admin_user),
                  session: AsyncSession = Depends(get_session)):
    req = await session.get(PaymentRequest, req_id)
    if not req:
        raise HTTPException(404, "request not found")
    sub = await approve_payment(session, req, admin.telegram_id)
    await session.commit()
    user = await session.get(User, req.user_id)
    background.add_task(telegram.notify_payment_result, user, True, ends_at=sub.ends_at)
    return {"ok": True, "ends_at": sub.ends_at}


class RejectBody(BaseModel):
    reason: str = "other"


@router.post("/payments/{req_id}/reject")
async def reject(req_id: int, body: RejectBody, background: BackgroundTasks, admin: User = Depends(admin_user),
                 session: AsyncSession = Depends(get_session)):
    req = await session.get(PaymentRequest, req_id)
    if not req:
        raise HTTPException(404, "request not found")
    await reject_payment(session, req, admin.telegram_id, body.reason)
    await session.commit()
    user = await session.get(User, req.user_id)
    background.add_task(telegram.notify_payment_result, user, False, reason=body.reason)
    return {"ok": True}


# ---------------------------------------------------------------- users

@router.get("/users")
async def list_users(q: str = "", status: str = "", _: User = Depends(admin_user),
                     session: AsyncSession = Depends(get_session)):
    stmt = select(User).order_by(User.id.desc()).limit(300)
    if q:
        like = f"%{q.strip()}%"
        conds = [User.full_name.ilike(like), User.phone.ilike(like)]
        if q.strip().isdigit():
            conds.append(User.telegram_id == int(q.strip()))
        stmt = stmt.where(or_(*conds))
    users = (await session.execute(stmt)).scalars().all()
    out = []
    for u in users:
        st = await effective_status(session, u)
        if status and st.value != status:
            continue
        sub = await active_subscription(session, u.id)
        out.append({"id": u.id, "telegram_id": u.telegram_id, "name": u.full_name, "phone": u.phone,
                    "status": st.value, "ends_at": sub.ends_at if sub else None,
                    "created_at": u.created_at, "last_seen": u.last_seen})
    return out


@router.get("/users/{user_id}")
async def user_detail(user_id: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    subs = (await session.execute(select(Subscription, Plan.name).outerjoin(Plan, Plan.id == Subscription.plan_id)
                                  .where(Subscription.user_id == u.id).order_by(Subscription.id.desc()))).all()
    attempts = (await session.execute(
        select(Attempt, Question.number).join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == u.id).order_by(Attempt.id.desc()).limit(50))).all()
    return {
        "id": u.id, "telegram_id": u.telegram_id, "name": u.full_name, "phone": u.phone,
        "status": (await effective_status(session, u)).value, "blocked": u.status == UserStatus.blocked,
        "created_at": u.created_at, "last_seen": u.last_seen, "ui_language": u.ui_language,
        "subscriptions": [{"id": s.id, "plan": name, "starts_at": s.starts_at, "ends_at": s.ends_at,
                           "source": s.source.value, "status": s.status.value} for s, name in subs],
        "attempts": [{"id": a.id, "number": n, "score": a.manual_score if a.manual_score is not None else a.score,
                      "state": a.state.value, "created_at": a.created_at} for a, n in attempts],
    }


class GrantBody(BaseModel):
    days: int = Field(gt=0, le=3650)
    plan_id: int | None = None
    reason: str = ""


@router.post("/users/{user_id}/grant")
async def grant(user_id: int, body: GrantBody, admin: User = Depends(admin_user),
                session: AsyncSession = Depends(get_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    if body.plan_id and not await session.get(Plan, body.plan_id):
        raise HTTPException(404, "plan not found")
    sub = await grant_days(session, u, body.days, body.plan_id, SubscriptionSource.gift)
    audit(session, admin.telegram_id, "subscription.grant", f"user:{u.id}",
          new={"days": body.days, "ends_at": sub.ends_at.isoformat()}, reason=body.reason or None)
    await session.commit()
    return {"ok": True, "ends_at": sub.ends_at}


@router.post("/subscriptions/{sub_id}/cancel")
async def cancel_subscription(sub_id: int, admin: User = Depends(admin_user),
                              session: AsyncSession = Depends(get_session)):
    s = await session.get(Subscription, sub_id)
    if not s:
        raise HTTPException(404, "subscription not found")
    s.status = SubscriptionStatus.cancelled
    u = await session.get(User, s.user_id)
    await session.flush()
    await sync_user_status(session, u)
    audit(session, admin.telegram_id, "subscription.cancel", f"subscription:{s.id}")
    await session.commit()
    return {"ok": True}


class BlockBody(BaseModel):
    blocked: bool
    reason: str = ""


@router.post("/users/{user_id}/block")
async def block(user_id: int, body: BlockBody, admin: User = Depends(admin_user),
                session: AsyncSession = Depends(get_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    if body.blocked:
        u.status = UserStatus.blocked
    else:
        u.status = UserStatus.guest
        await session.flush()
        await sync_user_status(session, u)
    audit(session, admin.telegram_id, "user.block" if body.blocked else "user.unblock", f"user:{u.id}",
          reason=body.reason or None)
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- plans

class PlanBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    days: int = Field(gt=0, le=3650)
    price_uzs: int = Field(ge=0)
    is_active: bool = True
    course_ids: list[int] = []


def plan_out(p: Plan) -> dict:
    return {"id": p.id, "name": p.name, "days": p.days, "price_uzs": p.price_uzs, "is_active": p.is_active,
            "course_ids": [c.id for c in p.courses]}


@router.get("/plans")
async def list_plans(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Plan).options(selectinload(Plan.courses)).order_by(Plan.id))).scalars()
    return [plan_out(p) for p in rows]


async def _apply_plan(session: AsyncSession, p: Plan, body: PlanBody) -> None:
    p.name, p.days, p.price_uzs, p.is_active = body.name.strip(), body.days, body.price_uzs, body.is_active
    p.courses = list((await session.execute(select(Course).where(Course.id.in_(body.course_ids)))).scalars()) \
        if body.course_ids else []


@router.post("/plans")
async def create_plan(body: PlanBody, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    p = Plan(name="", days=1, price_uzs=0)
    p.courses = []
    await _apply_plan(session, p, body)
    session.add(p)
    await session.flush()
    audit(session, admin.telegram_id, "plan.create", f"plan:{p.id}", new=body.model_dump())
    await session.commit()
    return {"id": p.id}


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: int, body: PlanBody, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    p = (await session.execute(select(Plan).options(selectinload(Plan.courses)).where(Plan.id == plan_id))) \
        .scalar_one_or_none()
    if not p:
        raise HTTPException(404, "plan not found")
    old = plan_out(p)
    await _apply_plan(session, p, body)
    audit(session, admin.telegram_id, "plan.update", f"plan:{p.id}", old=old, new=body.model_dump())
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- courses and topics

class CourseBody(BaseModel):
    name: dict[str, str]
    description: dict[str, str] | None = None
    is_published: bool = False


@router.get("/courses")
async def list_courses(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    counts = dict((await session.execute(select(Question.course_id, func.count()).group_by(Question.course_id))).all())
    courses = (await session.execute(select(Course).options(selectinload(Course.topics)).order_by(Course.id))).scalars()
    return [{"id": c.id, "name": c.name, "description": c.description, "is_published": c.is_published,
             "questions": counts.get(c.id, 0),
             "topics": [{"id": t.id, "name": t.name, "order": t.order}
                        for t in sorted(c.topics, key=lambda t: (t.order, t.id))]} for c in courses]


def _clean_names(d: dict[str, str] | None) -> dict | None:
    if d is None:
        return None
    return {k: v.strip() for k, v in d.items() if k in ("uz", "ru", "en") and v and v.strip()}


@router.post("/courses")
async def create_course(body: CourseBody, admin: User = Depends(admin_user),
                        session: AsyncSession = Depends(get_session)):
    name = _clean_names(body.name)
    if not name:
        raise HTTPException(400, "name required")
    c = Course(name=name, description=_clean_names(body.description), is_published=body.is_published)
    session.add(c)
    await session.flush()
    audit(session, admin.telegram_id, "course.create", f"course:{c.id}", new=body.model_dump())
    await session.commit()
    return {"id": c.id}


@router.put("/courses/{course_id}")
async def update_course(course_id: int, body: CourseBody, admin: User = Depends(admin_user),
                        session: AsyncSession = Depends(get_session)):
    c = await session.get(Course, course_id)
    if not c:
        raise HTTPException(404, "course not found")
    name = _clean_names(body.name)
    if not name:
        raise HTTPException(400, "name required")
    c.name, c.description, c.is_published = name, _clean_names(body.description), body.is_published
    audit(session, admin.telegram_id, "course.update", f"course:{c.id}", new=body.model_dump())
    await session.commit()
    return {"ok": True}


class TopicBody(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    order: int = 0


@router.post("/courses/{course_id}/topics")
async def create_topic(course_id: int, body: TopicBody, admin: User = Depends(admin_user),
                       session: AsyncSession = Depends(get_session)):
    if not await session.get(Course, course_id):
        raise HTTPException(404, "course not found")
    t = Topic(course_id=course_id, name=body.name.strip(), order=body.order)
    session.add(t)
    await session.commit()
    return {"id": t.id}


@router.put("/topics/{topic_id}")
async def update_topic(topic_id: int, body: TopicBody, admin: User = Depends(admin_user),
                       session: AsyncSession = Depends(get_session)):
    t = await session.get(Topic, topic_id)
    if not t:
        raise HTTPException(404, "topic not found")
    t.name, t.order = body.name.strip(), body.order
    await session.commit()
    return {"ok": True}


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    t = await session.get(Topic, topic_id)
    if not t:
        raise HTTPException(404, "topic not found")
    await session.execute(update(Question).where(Question.topic_id == topic_id).values(topic_id=None))
    await session.delete(t)
    audit(session, admin.telegram_id, "topic.delete", f"topic:{topic_id}", old={"name": t.name})
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- questions

class KeyPointBody(BaseModel):
    text: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0, le=100)


class QuestionBody(BaseModel):
    course_id: int
    topic_id: int | None = None
    number: int
    text: str = Field(min_length=1)
    model_answer: str = ""
    explanation: str | None = None
    is_active: bool = True
    key_points: list[KeyPointBody] = []


def question_out(q: Question) -> dict:
    return {"id": q.id, "course_id": q.course_id, "topic_id": q.topic_id, "number": q.number, "text": q.text,
            "model_answer": q.model_answer, "explanation": q.explanation, "is_active": q.is_active,
            "question_audio": file_id(q.question_audio), "answer_audio": file_id(q.answer_audio),
            "key_points": [{"id": k.id, "text": k.text, "weight": k.weight}
                           for k in sorted(q.key_points, key=lambda k: k.id)]}


@router.get("/courses/{course_id}/questions")
async def list_questions(course_id: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    qs = (await session.execute(select(Question).options(selectinload(Question.key_points))
                                .where(Question.course_id == course_id)
                                .order_by(Question.number, Question.id))).scalars()
    return [question_out(q) for q in qs]


async def _load_question(session: AsyncSession, qid: int) -> Question:
    q = (await session.execute(select(Question).options(selectinload(Question.key_points))
                               .where(Question.id == qid))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "question not found")
    return q


async def _check_refs(session: AsyncSession, body: QuestionBody) -> None:
    if not await session.get(Course, body.course_id):
        raise HTTPException(404, "course not found")
    if body.topic_id is not None:
        t = await session.get(Topic, body.topic_id)
        if not t or t.course_id != body.course_id:
            raise HTTPException(400, "topic is not in this course")


@router.post("/questions")
async def create_question(body: QuestionBody, admin: User = Depends(admin_user),
                          session: AsyncSession = Depends(get_session)):
    await _check_refs(session, body)
    q = Question(course_id=body.course_id, topic_id=body.topic_id, number=body.number, text=body.text.strip(),
                 model_answer=body.model_answer.strip(), explanation=(body.explanation or "").strip() or None,
                 is_active=body.is_active)
    q.key_points = [KeyPoint(text=k.text.strip(), weight=k.weight) for k in body.key_points]
    session.add(q)
    await session.flush()
    audit(session, admin.telegram_id, "question.create", f"question:{q.id}")
    await session.commit()
    return {"id": q.id}


@router.put("/questions/{question_id}")
async def update_question(question_id: int, body: QuestionBody, admin: User = Depends(admin_user),
                          session: AsyncSession = Depends(get_session)):
    q = await _load_question(session, question_id)
    await _check_refs(session, body)
    old = question_out(q)
    q.course_id, q.topic_id, q.number = body.course_id, body.topic_id, body.number
    q.text, q.model_answer = body.text.strip(), body.model_answer.strip()
    q.explanation, q.is_active = (body.explanation or "").strip() or None, body.is_active
    # Keep key point ids that are unchanged so past attempts still point at the same rows.
    existing = {(k.text, k.weight): k for k in q.key_points}
    keep, new = [], []
    for kb in body.key_points:
        k = existing.pop((kb.text.strip(), kb.weight), None)
        if k is not None:
            keep.append(k)
        else:
            new.append(KeyPoint(text=kb.text.strip(), weight=kb.weight))
    for k in existing.values():
        await session.delete(k)
    q.key_points = keep + new
    audit(session, admin.telegram_id, "question.update", f"question:{q.id}", old=old)
    await session.commit()
    return {"ok": True}


@router.delete("/questions/{question_id}")
async def delete_question(question_id: int, admin: User = Depends(admin_user),
                          session: AsyncSession = Depends(get_session)):
    q = await _load_question(session, question_id)
    used = (await session.execute(select(func.count()).select_from(Attempt).where(
        Attempt.question_id == q.id))).scalar_one()
    if used:  # answered questions are hidden, not deleted, so history stays intact
        q.is_active = False
        action = "question.deactivate"
    else:
        await session.execute(delete(KeyPoint).where(KeyPoint.question_id == q.id))
        await session.delete(q)
        action = "question.delete"
    audit(session, admin.telegram_id, action, f"question:{question_id}")
    await session.commit()
    return {"ok": True, "deactivated": bool(used)}


@router.post("/questions/{question_id}/audio")
async def upload_question_audio(question_id: int, kind: str = Form(...), audio: UploadFile = File(...),
                                admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    if kind not in ("question", "answer"):
        raise HTTPException(400, "kind must be question or answer")
    q = await _load_question(session, question_id)
    f = await store_upload(session, audio, "question_audio" if kind == "question" else "model_audio",
                           None, AUDIO_TYPES, MAX_AUDIO)
    old_id = file_id(q.question_audio if kind == "question" else q.answer_audio)
    if kind == "question":
        q.question_audio = file_ref(f)
    else:
        q.answer_audio = file_ref(f)
    if old_id:
        await session.execute(delete(StoredFile).where(StoredFile.id == old_id))
    audit(session, admin.telegram_id, f"question.audio.{kind}", f"question:{q.id}")
    await session.commit()
    return {"ok": True, "file": f.id}


@router.delete("/questions/{question_id}/audio/{kind}")
async def delete_question_audio(question_id: int, kind: str, admin: User = Depends(admin_user),
                                session: AsyncSession = Depends(get_session)):
    q = await _load_question(session, question_id)
    ref = q.question_audio if kind == "question" else q.answer_audio
    if kind == "question":
        q.question_audio = None
    else:
        q.answer_audio = None
    if file_id(ref):
        await session.execute(delete(StoredFile).where(StoredFile.id == file_id(ref)))
    await session.commit()
    return {"ok": True}


IMPORT_COLUMNS = ["number", "topic", "question", "model_answer", "key_points", "explanation"]


@router.get("/courses/{course_id}/export")
async def export_questions(course_id: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    from openpyxl import Workbook
    topics = {t.id: t.name for t in (await session.execute(select(Topic).where(Topic.course_id == course_id))).scalars()}
    qs = (await session.execute(select(Question).options(selectinload(Question.key_points))
                                .where(Question.course_id == course_id).order_by(Question.number))).scalars()
    wb = Workbook()
    ws = wb.active
    ws.title = "questions"
    ws.append(IMPORT_COLUMNS)
    for q in qs:
        kps = "\n".join(f"{k.text} | {k.weight:g}" if k.weight != 1 else k.text
                        for k in sorted(q.key_points, key=lambda k: k.id))
        ws.append([q.number, topics.get(q.topic_id, ""), q.text, q.model_answer, kps, q.explanation or ""])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="course-{course_id}-questions.xlsx"'})


def parse_key_points(cell) -> list[tuple[str, float]]:
    out = []
    for line in str(cell or "").replace("\r", "").split("\n"):
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        weight = 1.0
        if "|" in line:
            text, _, w = line.rpartition("|")
            try:
                weight = float(w.strip().replace(",", "."))
                line = text.strip()
            except ValueError:
                pass
        if line:
            out.append((line, weight if weight > 0 else 1.0))
    return out


def parse_import(data: bytes) -> list[dict]:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "not a valid .xlsx file")
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(400, "the sheet is empty")
    header = [str(h or "").strip().lower().replace(" ", "_") for h in rows[0]]
    aliases = {"savol": "question", "вопрос": "question", "javob": "model_answer", "ответ": "model_answer",
               "answer": "model_answer", "raqam": "number", "№": "number", "no": "number", "mavzu": "topic",
               "тема": "topic", "kalit_fikrlar": "key_points", "ключевые_моменты": "key_points",
               "izoh": "explanation", "пояснение": "explanation"}
    header = [aliases.get(h, h) for h in header]
    if "question" not in header:
        raise HTTPException(400, "first row must contain column headers, including 'question'")
    idx = {h: i for i, h in enumerate(header) if h in IMPORT_COLUMNS}
    items, auto_number = [], 0
    for r in rows[1:]:
        get = lambda k: (r[idx[k]] if k in idx and idx[k] < len(r) else None)  # noqa: E731
        text = str(get("question") or "").strip()
        if not text:
            continue
        auto_number += 1
        num = get("number")
        try:
            number = int(float(num)) if num not in (None, "") else auto_number
        except (TypeError, ValueError):
            number = auto_number
        items.append({"number": number, "topic": str(get("topic") or "").strip(), "text": text,
                      "model_answer": str(get("model_answer") or "").strip(),
                      "key_points": parse_key_points(get("key_points")),
                      "explanation": str(get("explanation") or "").strip() or None})
    if not items:
        raise HTTPException(400, "no questions found in the file")
    return items


@router.post("/courses/{course_id}/import")
async def import_questions(course_id: int, file: UploadFile = File(...), replace: bool = Form(False),
                           admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    """Excel import. Columns: number, topic, question, model_answer, key_points (one per line,
    optional "| weight"), explanation. Questions with an existing number are updated."""
    if not await session.get(Course, course_id):
        raise HTTPException(404, "course not found")
    items = parse_import(await file.read(20 * 1024 * 1024))
    topics = {t.name.lower(): t for t in
              (await session.execute(select(Topic).where(Topic.course_id == course_id))).scalars()}
    existing = {q.number: q for q in (await session.execute(
        select(Question).options(selectinload(Question.key_points))
        .where(Question.course_id == course_id))).scalars()}
    created = updated = 0
    for it in items:
        topic_id = None
        if it["topic"]:
            t = topics.get(it["topic"].lower())
            if t is None:
                t = Topic(course_id=course_id, name=it["topic"], order=len(topics))
                session.add(t)
                await session.flush()
                topics[it["topic"].lower()] = t
            topic_id = t.id
        q = existing.get(it["number"])
        if q is None:
            q = Question(course_id=course_id, number=it["number"], text=it["text"], model_answer=it["model_answer"],
                         explanation=it["explanation"], topic_id=topic_id, is_active=True)
            q.key_points = [KeyPoint(text=t, weight=w) for t, w in it["key_points"]]
            session.add(q)
            existing[it["number"]] = q
            created += 1
        else:
            q.text, q.model_answer, q.explanation = it["text"], it["model_answer"], it["explanation"]
            q.topic_id, q.is_active = topic_id, True
            if replace or it["key_points"]:
                old = {(k.text, k.weight): k for k in q.key_points}
                keep, new = [], []
                for t, w in it["key_points"]:
                    k = old.pop((t, w), None)
                    (keep.append(k) if k else new.append(KeyPoint(text=t, weight=w)))
                for k in old.values():
                    await session.delete(k)
                q.key_points = keep + new
            updated += 1
    audit(session, admin.telegram_id, "question.import", f"course:{course_id}",
          new={"created": created, "updated": updated})
    await session.commit()
    return {"created": created, "updated": updated}


@router.get("/import-template")
async def import_template(_: User = Depends(admin_user)):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "questions"
    ws.append(IMPORT_COLUMNS)
    ws.append([1, "Umumiy hamshiralik", "Qon bosimini o'lchash tartibini ayting.",
               "Bemorni 5 daqiqa tinch o'tirg'iziladi, manjeta yelkaga yurak darajasida taqiladi...",
               "Bemor 5 daqiqa dam oladi\nManjeta yurak darajasida | 2\nNatija yoziladi", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="questions-template.xlsx"'})


# ---------------------------------------------------------------- attempts (review)

@router.get("/attempts")
async def list_attempts(question_id: int | None = None, user_id: int | None = None, _: User = Depends(admin_user),
                        session: AsyncSession = Depends(get_session)):
    stmt = (select(Attempt, User.full_name, Question.number, Question.text)
            .join(User, User.id == Attempt.user_id).join(Question, Question.id == Attempt.question_id)
            .order_by(Attempt.id.desc()).limit(200))
    if question_id:
        stmt = stmt.where(Attempt.question_id == question_id)
    if user_id:
        stmt = stmt.where(Attempt.user_id == user_id)
    rows = (await session.execute(stmt)).all()
    return [{"id": a.id, "user_id": a.user_id, "user": name, "number": n, "question": t, "state": a.state.value,
             "mode": a.mode, "score": a.score, "manual_score": a.manual_score, "audio": file_id(a.audio_file),
             "transcript": a.transcript, "comment": a.comment, "created_at": a.created_at}
            for a, name, n, t in rows]


class ManualScore(BaseModel):
    score: float | None


@router.put("/attempts/{attempt_id}/score")
async def set_manual_score(attempt_id: int, body: ManualScore, admin: User = Depends(admin_user),
                           session: AsyncSession = Depends(get_session)):
    a = await session.get(Attempt, attempt_id)
    if not a:
        raise HTTPException(404, "attempt not found")
    old = a.manual_score
    a.manual_score = round_half(body.score) if body.score is not None else None
    if a.manual_score is not None and a.state != AttemptState.graded:
        a.state = AttemptState.graded
    audit(session, admin.telegram_id, "attempt.manual_score", f"attempt:{a.id}",
          old={"manual_score": old}, new={"manual_score": a.manual_score})
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- settings, files, logs

@router.get("/settings")
async def get_all_settings(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    s = await get_settings_map(session)
    for k in SECRET_SETTINGS:
        s[k] = "••••" + s[k][-4:] if s[k] else ""
    return s


@router.put("/settings")
async def save_settings(values: dict, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    clean = {}
    for k, v in values.items():
        if k in SECRET_SETTINGS and isinstance(v, str) and v.startswith("••••"):
            continue  # masked value sent back unchanged
        clean[k] = v
    await put_settings(session, clean)
    audit(session, admin.telegram_id, "settings.update", "settings",
          new={k: ("***" if k in SECRET_SETTINGS else v) for k, v in clean.items()})
    await session.commit()
    if "miniapp_url" in clean:
        from ..main import configure_bot
        await configure_bot()
    return {"ok": True, "keys": sorted(DEFAULT_SETTINGS)}


@router.get("/files/{fid}")
async def admin_file(fid: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    f = await session.get(StoredFile, fid)
    if not f:
        raise HTTPException(404, "file not found")
    return Response(f.data, media_type=f.content_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/logs")
async def logs(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(300))).scalars()
    return [{"id": r.id, "admin_id": r.admin_id, "action": r.action, "object": r.object, "old": r.old_value,
             "new": r.new_value, "reason": r.reason, "created_at": r.created_at} for r in rows]
