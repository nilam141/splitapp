from fastapi import APIRouter, Depends

from app.auth_deps import get_current_user
from app.models import User
from app.schemas import UserMe

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
def get_me(user: User = Depends(get_current_user)):
    return user
