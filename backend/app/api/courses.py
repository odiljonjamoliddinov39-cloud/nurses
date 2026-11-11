from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Course, User
from ..security import current_user

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
async def list_courses(_: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Course).where(Course.is_published.is_(True)))).scalars()
    return [{"id": c.id, "name": c.name, "description": c.description, "cover": c.cover} for c in rows]
