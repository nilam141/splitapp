from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services_auth
from app.db import get_db

from app.auth_deps import get_current_user
from app.models import User
from app.schemas import UserMe, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserMe)
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_auth.update_me(db, user, body)
