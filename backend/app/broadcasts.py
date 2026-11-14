"""Broadcasts: resolve a segment to Telegram users and deliver a message through the bot."""
import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import telegram
from .db import SessionLocal
from .models import Broadcast, StoredFile, Subscription, SubscriptionStatus, User, UserStatus
from .services import file_id, now_utc

log = logging.getLogger("uvicorn.error")

SEGMENTS = ("all", "subscribers", "expired", "guests")
CAPTION_LIMIT = 1024          # Telegram's photo caption limit
SEND_PAUSE = 0.05             # ~20 messages/second, under Telegram's 30/second limit
PROGRESS_EVERY = 25


def parse_segment(segment: str) -> tuple[str, int | None]:
    """'all' | 'subscribers' | 'expired' | 'guests' | 'course:<id>' -> (kind, course id)."""
    if segment in SEGMENTS:
        return segment, None
    kind, _, rest = segment.partition(":")
    if kind == "course" and rest.isdigit():
        return "course", int(rest)
    raise ValueError(f"unknown segment {segment!r}")


async def recipient_ids(session: AsyncSession, segment: str) -> list[int]:
    """Telegram ids of non-blocked users in the segment."""
    kind, course_id = parse_segment(segment)
    q = select(User.telegram_id).where(User.status != UserStatus.blocked)
    now = now_utc()
    active = select(Subscription.user_id).where(
        Subscription.status == SubscriptionStatus.active, Subscription.ends_at > now)
    ever = select(Subscription.user_id)
    if kind == "subscribers":
        q = q.where(User.id.in_(active))
    elif kind == "expired":
        q = q.where(User.id.in_(ever), User.id.not_in(active))
    elif kind == "guests":
        q = q.where(User.id.not_in(ever))
    elif kind == "course":
        q = q.where(User.course_id == course_id)
    return list((await session.execute(q.order_by(User.id))).scalars())


def keyboard(b: Broadcast) -> dict | None:
    btn = b.button or {}
    if btn.get("text") and btn.get("url"):
        return {"inline_keyboard": [[{"text": btn["text"], "url": btn["url"]}]]}
    return None


async def deliver(chat_id: int, b: Broadcast, image: StoredFile | None) -> bool:
    """Send one broadcast message; True if Telegram accepted it."""
    markup = keyboard(b)
    if image is not None and len(b.text) <= CAPTION_LIMIT:
        payload = {"chat_id": chat_id, "caption": b.text}
        if markup:
            payload["reply_markup"] = markup
        return await telegram.call("sendPhoto", payload, files={"photo": ("image", image.data, image.content_type)}) is not None
    if image is not None:  # too long for a caption: photo first, then the text with the button
        if await telegram.call("sendPhoto", {"chat_id": chat_id},
                               files={"photo": ("image", image.data, image.content_type)}) is None:
            return False
    payload = {"chat_id": chat_id, "text": b.text}
    if markup:
        payload["reply_markup"] = markup
    return await telegram.call("sendMessage", payload) is not None


async def load_image(session: AsyncSession, b: Broadcast) -> StoredFile | None:
    fid = file_id(b.image)
    return await session.get(StoredFile, fid) if fid else None


async def run_broadcast(broadcast_id: int) -> None:
    """Deliver a broadcast that is already marked 'sending'. Progress is saved as it goes."""
    async with SessionLocal() as session:
        b = await session.get(Broadcast, broadcast_id)
        if b is None:
            return
        try:
            recipients = await recipient_ids(session, b.segment)
            image = await load_image(session, b)
            b.total_count, b.sent_count, b.failed_count = len(recipients), 0, 0
            await session.commit()
            for n, chat_id in enumerate(recipients, 1):
                if await deliver(chat_id, b, image):
                    b.sent_count += 1
                else:
                    b.failed_count += 1  # user blocked the bot, deleted the chat, ...
                if n % PROGRESS_EVERY == 0:
                    await session.commit()
                await asyncio.sleep(SEND_PAUSE)
            b.status, b.sent_at = "sent", now_utc()
        except Exception:
            log.exception("broadcast %s failed", broadcast_id)
            b.status = "interrupted"
        await session.commit()


async def dispatch_due() -> int:
    """Claim every scheduled broadcast whose time has come (atomically) and send it."""
    async with SessionLocal() as session:
        ids = list((await session.execute(
            update(Broadcast).where(Broadcast.status == "scheduled", Broadcast.scheduled_at <= now_utc())
            .values(status="sending").returning(Broadcast.id))).scalars())
        await session.commit()
    for broadcast_id in ids:
        await run_broadcast(broadcast_id)
    return len(ids)
