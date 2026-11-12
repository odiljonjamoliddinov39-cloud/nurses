"""Auth: Telegram Mini App initData (users) and Telegram Login Widget sessions (admin panel in a browser)."""
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


def verify_login_widget(fields: dict, bot_token: str, max_age: int = 86400, now: float | None = None) -> dict:
    """Validate data from the Telegram Login Widget (browser sign-in); return the fields."""
    if not bot_token:
        raise InitDataError("bot token not configured")
    pairs = {k: str(v) for k, v in fields.items() if v is not None}
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("missing hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("bad signature")
    if (now if now is not None else time.time()) - int(pairs.get("auth_date", "0")) > max_age:
        raise InitDataError("expired")
    return pairs


def _session_key(bot_token: str) -> bytes:
    return hmac.new(b"AdminSession", bot_token.encode(), hashlib.sha256).digest()


def make_admin_session(telegram_id: int, bot_token: str, ttl: int, now: float | None = None) -> tuple[str, int]:
    """Signed token ``<telegram_id>.<expires>.<sig>`` for the browser admin panel."""
    expires = int(now if now is not None else time.time()) + ttl
    body = f"{telegram_id}.{expires}"
    sig = hmac.new(_session_key(bot_token), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}", expires


def read_admin_session(token: str, bot_token: str, now: float | None = None) -> int:
    """Return the Telegram ID in a valid, unexpired admin session token."""
    if not bot_token:
        raise InitDataError("bot token not configured")
    try:
        tg_id, expires, sig = token.split(".")
        body = f"{int(tg_id)}.{int(expires)}"
    except ValueError:
        raise InitDataError("malformed session")
    expected = hmac.new(_session_key(bot_token), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise InitDataError("bad session signature")
    if (now if now is not None else time.time()) > int(expires):
        raise InitDataError("session expired")
    return int(tg_id)


async def upsert_user(session: AsyncSession, tg_id: int, full_name: str | None) -> User:
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
    return await upsert_user(session, tg_id, full_name)


async def admin_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Admin panel auth: ``Bearer <session>`` from a browser login, or ``tma <initData>`` inside Telegram."""
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() == "bearer" and raw:
        if not settings.bot_token:
            raise HTTPException(503, "server misconfigured: BOT_TOKEN not set")
        try:
            tg_id = read_admin_session(raw, settings.bot_token)
        except InitDataError as exc:
            raise HTTPException(401, f"invalid session: {exc}")
        if tg_id not in settings.admin_ids:
            raise HTTPException(403, "admin only")
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            user = await upsert_user(session, tg_id, None)
        if user.status == UserStatus.blocked:
            raise HTTPException(403, "blocked")
        return user
    user = await current_user(authorization, session, settings)
    if user.telegram_id not in settings.admin_ids:
        raise HTTPException(403, "admin only")
    return user
