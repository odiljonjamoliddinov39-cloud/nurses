from fastapi import APIRouter, Depends

from ..models import User
from ..security import admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me")
async def admin_me(user: User = Depends(admin_user)):
    """200 only for Telegram IDs on the admin list; the admin panel gates on this."""
    return {"telegram_id": user.telegram_id, "is_admin": True}
