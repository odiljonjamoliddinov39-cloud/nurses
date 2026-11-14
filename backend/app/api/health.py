import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session

router = APIRouter()


def running_version() -> str:
    """Short id of the deployed commit (Railway sets RAILWAY_GIT_COMMIT_SHA), so you can tell which version is live."""
    sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("GIT_COMMIT") or ""
    return sha[:7] or "unknown"


@router.get("/health")
async def health():
    """Liveness: the process is up."""
    return {"status": "ok", "version": running_version()}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)):
    """Readiness: required dependencies (PostgreSQL) are reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"status": "ready"}
