from fastapi import APIRouter, Depends

from ..models import User
from ..security import current_user

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "ui_language": user.ui_language,
        "status": user.status,
    }
