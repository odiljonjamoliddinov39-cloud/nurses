"""Admin broadcasts: write a message, pick a segment, send now or schedule it."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import broadcasts as bc
from ..db import get_session
from ..models import Broadcast, Course, User
from ..security import admin_user
from ..services import IMAGE_TYPES, MAX_IMAGE, audit, file_id, file_ref, now_utc, store_upload

router = APIRouter(prefix="/admin/broadcasts", tags=["admin"])
EDITABLE = ("draft", "scheduled")


class BroadcastIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    segment: str = "all"
    button_text: str | None = Field(default=None, max_length=60)
    button_url: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None  # ISO 8601; a time without zone is read as UTC
    send_now: bool = False


def out(b: Broadcast) -> dict:
    return {"id": b.id, "text": b.text, "segment": b.segment, "button": b.button, "image": file_id(b.image),
            "status": b.status, "scheduled_at": b.scheduled_at, "sent_at": b.sent_at, "created_at": b.created_at,
            "total": b.total_count, "sent": b.sent_count, "failed": b.failed_count}


async def check(session: AsyncSession, body: BroadcastIn) -> dict | None:
    try:
        kind, course_id = bc.parse_segment(body.segment)
    except ValueError:
        raise HTTPException(400, "segment must be all, subscribers, expired, guests or course:<id>")
    if kind == "course" and not await session.get(Course, course_id):
        raise HTTPException(404, "course not found")
    text, url = (body.button_text or "").strip(), (body.button_url or "").strip()
    if bool(text) != bool(url):
        raise HTTPException(400, "a button needs both a label and a link")
    if url and not url.startswith("https://"):
        raise HTTPException(400, "the button link must start with https://")
    return {"text": text, "url": url} if text else None


def schedule(b: Broadcast, body: BroadcastIn) -> None:
    if body.send_now:
        b.status, b.scheduled_at = "scheduled", now_utc()
    elif body.scheduled_at is not None:
        when = body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=timezone.utc)
        if when <= now_utc():
            raise HTTPException(400, "the scheduled time is in the past")
        b.status, b.scheduled_at = "scheduled", when
    else:
        b.status, b.scheduled_at = "draft", None


async def load(session: AsyncSession, broadcast_id: int, *, editable: bool = False) -> Broadcast:
    b = await session.get(Broadcast, broadcast_id)
    if b is None:
        raise HTTPException(404, "broadcast not found")
    if editable and b.status not in EDITABLE:
        raise HTTPException(409, f"a {b.status} broadcast cannot be changed")
    return b


@router.get("")
async def list_broadcasts(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Broadcast).order_by(Broadcast.id.desc()).limit(50))).scalars()
    return [out(b) for b in rows]


@router.get("/preview")
async def preview(segment: str = "all", _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    """How many people a segment reaches."""
    try:
        return {"count": len(await bc.recipient_ids(session, segment))}
    except ValueError:
        raise HTTPException(400, "unknown segment")


@router.post("")
async def create(body: BroadcastIn, background: BackgroundTasks, admin: User = Depends(admin_user),
                 session: AsyncSession = Depends(get_session)):
    button = await check(session, body)
    b = Broadcast(text=body.text.strip(), segment=body.segment, button=button, created_by=admin.telegram_id)
    schedule(b, body)
    session.add(b)
    await session.flush()
    audit(session, admin.telegram_id, "broadcast.create", f"broadcast:{b.id}", new={"segment": b.segment, "status": b.status})
    await session.commit()
    if body.send_now:
        background.add_task(bc.dispatch_due)
    return out(b)


@router.put("/{broadcast_id}")
async def update(broadcast_id: int, body: BroadcastIn, background: BackgroundTasks,
                 admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    b = await load(session, broadcast_id, editable=True)
    b.button = await check(session, body)
    b.text, b.segment = body.text.strip(), body.segment
    schedule(b, body)
    audit(session, admin.telegram_id, "broadcast.update", f"broadcast:{b.id}")
    await session.commit()
    if body.send_now:
        background.add_task(bc.dispatch_due)
    return out(b)


@router.post("/{broadcast_id}/image")
async def set_image(broadcast_id: int, image: UploadFile = File(...), admin: User = Depends(admin_user),
                    session: AsyncSession = Depends(get_session)):
    b = await load(session, broadcast_id, editable=True)
    f = await store_upload(session, image, "broadcast_image", admin.id, IMAGE_TYPES, MAX_IMAGE)
    b.image = file_ref(f)
    await session.commit()
    return out(b)


@router.delete("/{broadcast_id}/image")
async def remove_image(broadcast_id: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    b = await load(session, broadcast_id, editable=True)
    b.image = None
    await session.commit()
    return out(b)


@router.post("/{broadcast_id}/send")
async def send_now(broadcast_id: int, background: BackgroundTasks, admin: User = Depends(admin_user),
                   session: AsyncSession = Depends(get_session)):
    b = await load(session, broadcast_id, editable=True)
    b.status, b.scheduled_at = "scheduled", now_utc()
    audit(session, admin.telegram_id, "broadcast.send", f"broadcast:{b.id}", new={"segment": b.segment})
    await session.commit()
    background.add_task(bc.dispatch_due)
    return out(b)


@router.post("/{broadcast_id}/test")
async def send_test(broadcast_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    """Send the message to the admin only, to see how it looks."""
    b = await load(session, broadcast_id)
    ok = await bc.deliver(admin.telegram_id, b, await bc.load_image(session, b))
    return {"ok": ok}


@router.delete("/{broadcast_id}")
async def delete(broadcast_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    b = await load(session, broadcast_id, editable=True)
    audit(session, admin.telegram_id, "broadcast.delete", f"broadcast:{b.id}")
    await session.delete(b)
    await session.commit()
    return {"ok": True}
