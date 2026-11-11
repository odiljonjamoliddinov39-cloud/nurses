"""Telegram Mini App initData verification and auth dependencies."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import get_session
from .models import User, UserStatus


class InitDataError(ValueError):
    pass


def verify_init_data(init_data: str, bot_token: str, max_age: int = 86400, now: float | None = None) -> dict:
    """Validate Telegram WebApp initData; return the parsed fields (``user`` decoded)."""
    if not bot_token:
        # An empty token gives a publicly reproducible signing key: never verify with it.
        raise InitDataError("bot token not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("missing hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("bad signature")
    auth_date = int(pairs.get("auth_date", "0"))
    if (now if now is not None else time.time()) - auth_date > max_age:
        raise InitDataError("expired")
    if "user" in pairs:
        pairs["user"] = json.loads(pairs["user"])
    return pairs


async def current_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Authorization header format: ``tma <initData>``."""
    if not settings.bot_token:
        raise HTTPException(503, "server misconfigured: BOT_TOKEN not set")
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "tma" or not raw:
        raise HTTPException(401, "missing initData")
    try:
        data = verify_init_data(raw, settings.bot_token, settings.init_data_max_age_seconds)
    except (InitDataError, ValueError) as exc:
        raise HTTPException(401, f"invalid initData: {exc}")
    tg = data.get("user") or {}
    tg_id = tg.get("id")
    if not tg_id:
        raise HTTPException(401, "no user in initData")
    full_name = " ".join(p for p in (tg.get("first_name"), tg.get("last_name")) if p) or None
    # Atomic first-login: concurrent requests for a new user cannot violate the unique key.
    await session.execute(
        pg_insert(User).values(telegram_id=tg_id, full_name=full_name, ui_language="uz")
        .on_conflict_do_nothing(index_elements=[User.telegram_id]))
    user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one()
    now = datetime.now(timezone.utc)
    if user.last_seen is None or (now - user.last_seen).total_seconds() > 60:
        user.last_seen = now
    await session.commit()
    if user.status == UserStatus.blocked:
        raise HTTPException(403, "blocked")
    return user


async def admin_user(user: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> User:
    if user.telegram_id not in settings.admin_ids:
        raise HTTPException(403, "admin only")
    return user
