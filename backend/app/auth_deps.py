"""Bearer-token authentication dependency for protected routes."""
import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import ApiError
from app.models import User


def _invalid() -> ApiError:
    return ApiError(401, "TOKEN_INVALID", "Invalid or expired access token")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _invalid()
    try:
        claims = jwt.decode(
            token.strip(),
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        if claims.get("type") != "access":
            raise _invalid()
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise _invalid()
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or not user.is_registered:
        raise _invalid()
    return user
