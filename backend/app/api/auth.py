"""Admin password sign-in and password change."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import admin_password as pw
from ..config import Settings, get_settings
from ..db import get_session
from ..models import User
from ..security import admin_user, make_admin_session, upsert_user
from ..services import audit

router = APIRouter(prefix="/admin", tags=["admin"])


class PasswordLogin(BaseModel):
    password: str = Field(min_length=1, max_length=pw.MAX_LEN)


class PasswordChange(BaseModel):
    current: str = Field(default="", max_length=pw.MAX_LEN)
    new: str = Field(min_length=pw.MIN_LEN, max_length=pw.MAX_LEN)


@router.post("/login-password")
async def login_password(body: PasswordLogin, session: AsyncSession = Depends(get_session),
                         settings: Settings = Depends(get_settings)):
    if not settings.bot_token:
        raise HTTPException(503, "server misconfigured: BOT_TOKEN not set")
    if not settings.admin_ids:
        raise HTTPException(503, "server misconfigured: ADMIN_TELEGRAM_IDS is empty")
    if pw.locked():
        raise HTTPException(429, "too many wrong passwords: wait 5 minutes (a code from the bot still works)")
    if not await pw.is_set(session, settings.admin_password):
        raise HTTPException(401, "no password is set yet: send /password to the bot to get one")
    if not await pw.check(session, body.password, settings.admin_password):
        pw.record_fail()
        raise HTTPException(401, "wrong password (forgot it? send /password to the bot for a new one)")
    admin_id = settings.primary_admin_id
    await upsert_user(session, admin_id, None)
    token, expires = make_admin_session(admin_id, settings.bot_token, settings.admin_session_ttl_seconds)
    return {"token": token, "expires_at": expires}


@router.get("/password-status")
async def password_status(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session),
                          settings: Settings = Depends(get_settings)):
    return {"set": await pw.is_set(session, settings.admin_password)}


@router.post("/password")
async def change_password(body: PasswordChange, admin: User = Depends(admin_user),
                          session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    """Set or change the admin password. Once one exists, the current password is required."""
    if await pw.is_set(session, settings.admin_password):
        if pw.locked():
            raise HTTPException(429, "too many wrong passwords: wait 5 minutes")
        if not await pw.check(session, body.current, settings.admin_password):
            pw.record_fail()
            raise HTTPException(403, "the current password is wrong")
        if body.new == body.current:
            raise HTTPException(400, "choose a different password")
    if len(set(body.new)) < 4:
        raise HTTPException(400, "that password is too simple: use at least 4 different characters")
    await pw.set_password(session, body.new)
    audit(session, admin.telegram_id, "admin.password.change", "admin")
    await session.commit()
    return {"ok": True}
