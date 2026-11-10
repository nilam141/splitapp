from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import services_auth
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return services_auth.register(db, body)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    return services_auth.login(db, body.email, body.password)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    return services_auth.refresh(db, body.refresh_token)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_auth.logout(db, user, body.refresh_token)
    return Response(status_code=204)
