"""Admin sign-in with a one-time code sent by the bot (no Telegram widget, domain registration or extra settings).

The admin sends /admin to the bot; the bot replies with a code that works once for 10 minutes. The admin page
exchanges it for a session. Only admin Telegram IDs can get a code; wrong guesses lock the endpoint for a while.
"""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LoginCode
from .services import now_utc

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L: easy to read and type
CODE_LEN = 8
TTL = timedelta(minutes=10)
MAX_FAILS, WINDOW_SECONDS = 10, 300

_fails: list[float] = []  # timestamps of recent wrong codes (this server process)


def normalise(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def hash_code(code: str, bot_token: str) -> str:
    return hmac.new(f"admin-code:{bot_token}".encode(), normalise(code).encode(), hashlib.sha256).hexdigest()


def locked(now: float | None = None) -> bool:
    now = time.time() if now is None else now
    _fails[:] = [t for t in _fails if now - t < WINDOW_SECONDS]
    return len(_fails) >= MAX_FAILS


def record_fail(now: float | None = None) -> None:
    _fails.append(time.time() if now is None else now)


def reset_fails() -> None:
    _fails.clear()


async def issue_code(session: AsyncSession, telegram_id: int, bot_token: str) -> str:
    """A fresh code for this admin; older unused codes of theirs stop working."""
    now = now_utc()
    await session.execute(delete(LoginCode).where(
        (LoginCode.telegram_id == telegram_id) | (LoginCode.expires_at < now - timedelta(days=1))))
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    session.add(LoginCode(code_hash=hash_code(code, bot_token), telegram_id=telegram_id, expires_at=now + TTL))
    await session.commit()
    return code


async def redeem(session: AsyncSession, code: str, bot_token: str) -> int | None:
    """Telegram id the code belongs to, or None. Atomic: a code can be used only once."""
    if len(normalise(code)) != CODE_LEN:
        return None
    now = now_utc()
    row = (await session.execute(
        update(LoginCode).where(LoginCode.code_hash == hash_code(code, bot_token), LoginCode.used_at.is_(None),
                                LoginCode.expires_at > now)
        .values(used_at=now).returning(LoginCode.telegram_id))).first()
    await session.commit()
    return row[0] if row else None
