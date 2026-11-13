"""Business rules shared by the Mini App API, the admin API and the Telegram webhook."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (AuditLog, PaymentRequest, PaymentStatus, Plan, Question, Setting,
                     StoredFile, Subscription, SubscriptionSource, SubscriptionStatus, User, UserStatus)

# ---------------------------------------------------------------- settings

DEFAULT_SETTINGS: dict = {
    "card_number": "",
    "card_holder": "",
    "payment_note": "",          # extra instructions shown on the payment screen
    "free_questions": 3,         # questions a guest can answer per course
    "daily_cap": 60,             # answers per user per day
    "grading_mode": "self",      # "self" (user ticks key points) or "ai" (Gemini)
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "ai_rules": "",              # extra grading rules appended to the AI prompt
    "support_contact": "",       # e.g. @username shown to blocked users and in Profile
    "miniapp_url": "",           # https URL of the Mini App (menu button / "Open app")
    "welcome_text": "",
    "max_answer_seconds": 180,
}
SECRET_SETTINGS = {"gemini_api_key"}


async def get_settings_map(session: AsyncSession) -> dict:
    rows = (await session.execute(select(Setting))).scalars()
    data = dict(DEFAULT_SETTINGS)
    for r in rows:
        if r.key in DEFAULT_SETTINGS and r.value is not None:
            data[r.key] = r.value.get("v") if isinstance(r.value, dict) else r.value
    return data


async def get_setting(session: AsyncSession, key: str):
    return (await get_settings_map(session))[key]


async def put_settings(session: AsyncSession, values: dict) -> None:
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            raise HTTPException(400, f"unknown setting {key}")
        default = DEFAULT_SETTINGS[key]
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be a number")
        elif isinstance(default, str):
            value = "" if value is None else str(value).strip()
        if key == "grading_mode" and value not in ("self", "ai"):
            raise HTTPException(400, "grading_mode must be self or ai")
        row = await session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value={"v": value}))
        else:
            row.value = {"v": value}


# ---------------------------------------------------------------- audit

def audit(session: AsyncSession, admin_id: int, action: str, obj: str,
          old=None, new=None, reason: str | None = None) -> None:
    session.add(AuditLog(admin_id=admin_id, action=action, object=obj,
                         old_value=old, new_value=new, reason=reason))


# ---------------------------------------------------------------- files

AUDIO_TYPES = ("audio/", "video/webm", "video/mp4", "application/ogg")
IMAGE_TYPES = ("image/",)
MAX_AUDIO = 15 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


async def store_upload(session: AsyncSession, upload: UploadFile, kind: str, owner: int | None,
                       allowed: tuple[str, ...], max_size: int) -> StoredFile:
    content_type = (upload.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if not content_type.startswith(allowed):
        raise HTTPException(415, f"unsupported file type {content_type}")
    data = await upload.read(max_size + 1)
    if len(data) > max_size:
        raise HTTPException(413, "file too large")
    if not data:
        raise HTTPException(400, "empty file")
    f = StoredFile(owner_user_id=owner, kind=kind, content_type=content_type, size=len(data), data=data)
    session.add(f)
    await session.flush()
    return f


def file_ref(f: StoredFile | None) -> str | None:
    return f"file:{f.id}" if f else None


def file_id(ref: str | None) -> int | None:
    if ref and ref.startswith("file:"):
        try:
            return int(ref[5:])
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- subscriptions and access

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    return (await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == SubscriptionStatus.active,
               Subscription.ends_at > now_utc())
        .order_by(Subscription.ends_at.desc()).limit(1))).scalar_one_or_none()


async def subscription_covers(session: AsyncSession, sub: Subscription | None, course_id: int) -> bool:
    if sub is None:
        return False
    if sub.plan_id is None:  # gift without a plan: every course
        return True
    plan = (await session.execute(
        select(Plan).options(selectinload(Plan.courses)).where(Plan.id == sub.plan_id))).scalar_one_or_none()
    if plan is None or not plan.courses:  # a plan with no courses listed covers all
        return True
    return any(c.id == course_id for c in plan.courses)


async def effective_status(session: AsyncSession, user: User) -> UserStatus:
    if user.status == UserStatus.blocked:
        return UserStatus.blocked
    if await active_subscription(session, user.id):
        return UserStatus.subscriber
    pending = (await session.execute(select(func.count()).select_from(PaymentRequest).where(
        PaymentRequest.user_id == user.id, PaymentRequest.status == PaymentStatus.pending))).scalar_one()
    if pending:
        return UserStatus.pending
    had = (await session.execute(select(func.count()).select_from(Subscription).where(
        Subscription.user_id == user.id))).scalar_one()
    return UserStatus.expired if had else UserStatus.guest


async def free_question_ids(session: AsyncSession, course_id: int, free: int) -> set[int]:
    if free <= 0:
        return set()
    rows = (await session.execute(
        select(Question.id).where(Question.course_id == course_id, Question.is_active.is_(True))
        .order_by(Question.number, Question.id).limit(free))).scalars()
    return set(rows)


async def can_answer(session: AsyncSession, user: User, question: Question) -> bool:
    """The single gate for paid actions."""
    if user.status == UserStatus.blocked:
        return False
    sub = await active_subscription(session, user.id)
    if await subscription_covers(session, sub, question.course_id):
        return True
    free = int(await get_setting(session, "free_questions"))
    return question.id in await free_question_ids(session, question.course_id, free)


async def sync_user_status(session: AsyncSession, user: User) -> None:
    if user.status != UserStatus.blocked:
        user.status = await effective_status(session, user)


async def grant_days(session: AsyncSession, user: User, days: int, plan_id: int | None,
                     source: SubscriptionSource) -> Subscription:
    """Start a subscription, or extend the current one so paid days are never lost."""
    if days <= 0:
        raise HTTPException(400, "days must be positive")
    current = await active_subscription(session, user.id)
    start = current.ends_at if current else now_utc()
    sub = Subscription(user_id=user.id, plan_id=plan_id, starts_at=start,
                       ends_at=start + timedelta(days=days), source=source,
                       status=SubscriptionStatus.active)
    session.add(sub)
    await session.flush()
    await sync_user_status(session, user)
    return sub


async def new_payment_code(session: AsyncSession) -> str:
    for _ in range(20):
        code = f"#{secrets.randbelow(9000) + 1000}"
        exists = (await session.execute(select(PaymentRequest.id).where(
            PaymentRequest.payment_code == code))).first()
        if not exists:
            return code
    return f"#{secrets.token_hex(3).upper()}"


async def approve_payment(session: AsyncSession, req: PaymentRequest, admin_tg: int) -> Subscription:
    if req.status != PaymentStatus.pending:
        raise HTTPException(409, f"request already {req.status.value}")
    plan = await session.get(Plan, req.plan_id)
    user = await session.get(User, req.user_id)
    if plan is None or user is None:
        raise HTTPException(404, "plan or user missing")
    sub = await grant_days(session, user, plan.days, plan.id, SubscriptionSource.payment)
    req.status = PaymentStatus.approved
    req.reviewed_by = admin_tg
    req.reviewed_at = now_utc()
    await sync_user_status(session, user)
    audit(session, admin_tg, "payment.approve", f"payment:{req.id}",
          new={"user_id": user.id, "plan_id": plan.id, "ends_at": sub.ends_at.isoformat()})
    return sub


async def reject_payment(session: AsyncSession, req: PaymentRequest, admin_tg: int, reason: str) -> None:
    if req.status != PaymentStatus.pending:
        raise HTTPException(409, f"request already {req.status.value}")
    req.status = PaymentStatus.rejected
    req.reject_reason = (reason or "other")[:300]
    req.reviewed_by = admin_tg
    req.reviewed_at = now_utc()
    user = await session.get(User, req.user_id)
    if user:
        await sync_user_status(session, user)
    audit(session, admin_tg, "payment.reject", f"payment:{req.id}", reason=req.reject_reason)


def round_half(x: float) -> float:
    return max(0.0, min(5.0, round(x * 2) / 2))
