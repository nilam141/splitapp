from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import services_auth
from app.config import settings
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import AuthResponse, LoginRequest, PasswordResetConfirm, PasswordResetRequest, RefreshRequest, RegisterRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    n = settings.trusted_proxy_count
    if n <= 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return parts[-n] if len(parts) >= n else peer


@router.post("/register", status_code=201, response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return services_auth.register(db, body)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return services_auth.login(db, body.email, body.password, client_ip(request))


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    return services_auth.refresh(db, body.refresh_token)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_auth.logout(db, user, body.refresh_token)
    return Response(status_code=204)


@router.post("/password-reset", status_code=202)
def request_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    services_auth.request_password_reset(db, body.email)
    return Response(status_code=202)


@router.post("/password-reset/confirm", response_model=AuthResponse)
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    return services_auth.confirm_password_reset(db, body.token, body.new_password)
