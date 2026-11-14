"""Admin promo codes: a percent or fixed discount with an optional usage limit and expiry."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import PromoCode, User
from ..security import admin_user
from ..services import audit, now_utc

router = APIRouter(prefix="/admin/promos", tags=["admin"])


class PromoIn(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    kind: Literal["percent", "fixed"]
    value: int = Field(gt=0, le=100_000_000)
    max_uses: int | None = Field(default=None, ge=1, le=1_000_000)
    expires_at: datetime | None = None  # a time without zone is read as UTC
    is_active: bool = True


def out(p: PromoCode) -> dict:
    return {"id": p.id, "code": p.code, "kind": p.kind, "value": p.value, "max_uses": p.max_uses,
            "used_count": p.used_count, "expires_at": p.expires_at, "is_active": p.is_active,
            "expired": bool(p.expires_at and p.expires_at <= now_utc()), "created_at": p.created_at}


def utc(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check(body: PromoIn) -> None:
    if body.kind == "percent" and body.value > 99:
        raise HTTPException(400, "a percent discount must be between 1 and 99")


@router.get("")
async def list_promos(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    return [out(p) for p in (await session.execute(select(PromoCode).order_by(PromoCode.id.desc()))).scalars()]


@router.post("")
async def create_promo(body: PromoIn, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    check(body)
    p = PromoCode(code=body.code.upper(), kind=body.kind, value=body.value, max_uses=body.max_uses,
                  expires_at=utc(body.expires_at), is_active=body.is_active)
    session.add(p)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "this code already exists")
    audit(session, admin.telegram_id, "promo.create", f"promo:{p.code}", new={"kind": p.kind, "value": p.value})
    await session.commit()
    return out(p)


@router.put("/{promo_id}")
async def update_promo(promo_id: int, body: PromoIn, admin: User = Depends(admin_user),
                       session: AsyncSession = Depends(get_session)):
    """Limit, expiry and on/off can always change; code, kind and value only before the first use."""
    check(body)
    p = await session.get(PromoCode, promo_id)
    if p is None:
        raise HTTPException(404, "promo code not found")
    if p.used_count and (body.code.upper() != p.code or body.kind != p.kind or body.value != p.value):
        raise HTTPException(409, "this code was already used: only the limit, expiry and on/off can change")
    if body.max_uses is not None and body.max_uses < p.used_count:
        raise HTTPException(400, f"the limit cannot be below the {p.used_count} uses already made")
    p.code, p.kind, p.value = body.code.upper(), body.kind, body.value
    p.max_uses, p.expires_at, p.is_active = body.max_uses, utc(body.expires_at), body.is_active
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "this code already exists")
    audit(session, admin.telegram_id, "promo.update", f"promo:{p.code}")
    await session.commit()
    return out(p)


@router.delete("/{promo_id}")
async def delete_promo(promo_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    p = await session.get(PromoCode, promo_id)
    if p is None:
        raise HTTPException(404, "promo code not found")
    if p.used_count:
        raise HTTPException(409, "this code was already used: switch it off instead of deleting it")
    audit(session, admin.telegram_id, "promo.delete", f"promo:{p.code}")
    await session.delete(p)
    await session.commit()
    return {"ok": True}
