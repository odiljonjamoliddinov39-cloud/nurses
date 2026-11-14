"""Admin panel password: stored as a salted scrypt hash. There is deliberately NO built-in default password (the
repository is public): the bot's /password command sends the admin a random one, and ADMIN_PASSWORD may set an
initial one. A password changed in the panel always wins over the environment value."""
import base64
import hashlib
import hmac
import os
import secrets
import time

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Setting

KEY = "admin_password_hash"   # a settings row; get_settings_map ignores unknown keys, so it never reaches the API
MIN_LEN, MAX_LEN = 10, 200
N, R, P = 2**14, 8, 1
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

MAX_FAILS, WINDOW_SECONDS = 10, 300
_fails: list[float] = []


def locked(now: float | None = None) -> bool:
    now = time.time() if now is None else now
    _fails[:] = [t for t in _fails if now - t < WINDOW_SECONDS]
    return len(_fails) >= MAX_FAILS


def record_fail(now: float | None = None) -> None:
    _fails.append(time.time() if now is None else now)


def reset_fails() -> None:
    _fails.clear()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def generate_password() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


async def stored_hash(session: AsyncSession) -> str | None:
    row = await session.get(Setting, KEY)
    return (row.value or {}).get("v") if row else None


async def is_set(session: AsyncSession, env_default: str) -> bool:
    return bool(await stored_hash(session) or env_default)


async def check(session: AsyncSession, password: str, env_default: str) -> bool:
    if not password or len(password) > MAX_LEN:
        return False
    stored = await stored_hash(session)
    if stored:
        return verify_password(password, stored)
    if env_default:
        return hmac.compare_digest(password.encode(), env_default.encode())
    return False


async def set_password(session: AsyncSession, password: str) -> None:
    """Caller commits."""
    row = await session.get(Setting, KEY)
    value = {"v": hash_password(password)}
    if row is None:
        session.add(Setting(key=KEY, value=value))
    else:
        row.value = value
