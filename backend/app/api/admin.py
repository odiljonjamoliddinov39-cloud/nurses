from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..models import User
from ..security import InitDataError, admin_user, make_admin_session, upsert_user, verify_login_widget

router = APIRouter(prefix="/admin", tags=["admin"])


class TelegramLogin(BaseModel):
    """Fields sent by the Telegram Login Widget; any extra field is part of the signature."""
    model_config = ConfigDict(extra="allow")
    id: int
    auth_date: int
    hash: str


@router.post("/login")
async def admin_login(
    body: TelegramLogin,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
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
