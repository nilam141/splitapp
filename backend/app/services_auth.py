from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.config import settings
from app.errors import ApiError
from app.models import Currency, RefreshToken, User
from app.schemas import AuthResponse, RegisterRequest, TokenPair, UserMe

NOTIFICATION_KEYS = (
    "expense_added", "expense_updated", "comment_added", "added_to_group", "removed_from_group",
    "group_updated", "friend_added", "friend_removed", "payment_recorded", "reminder",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _issue_tokens(db: Session, user: User) -> TokenPair:
    token, token_hash = security.new_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=_utcnow() + timedelta(days=settings.refresh_token_days),
    ))
    return TokenPair(
        access_token=security.create_access_token(user.id),
        refresh_token=token,
        token_type="bearer",
        expires_in=settings.access_token_seconds,
    )


def _auth_response(db: Session, user: User) -> AuthResponse:
    pair = _issue_tokens(db, user)
    return AuthResponse(**pair.model_dump(), user=UserMe.model_validate(user))


def register(db: Session, req: RegisterRequest) -> AuthResponse:
    email = req.email.lower()
    currency = req.default_currency.upper()
    if db.get(Currency, currency) is None:
        raise ApiError(422, "CURRENCY_UNKNOWN", "Unsupported currency", {"currency": currency})

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None and existing.is_registered:
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists", {"field": "email"})

    if existing is not None:  # claim a placeholder created by an invite
        user = existing
        user.name = req.name
        user.password_hash = security.hash_password(req.password)
        user.is_registered = True
        user.default_currency = currency
        user.time_zone = req.time_zone
    else:
        user = User(
            email=email,
            name=req.name,
            password_hash=security.hash_password(req.password),
            is_registered=True,
            default_currency=currency,
            time_zone=req.time_zone,
            notification_prefs={k: True for k in NOTIFICATION_KEYS},
            friend_code=_unused_friend_code(db),
        )
        db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists", {"field": "email"})
    resp = _auth_response(db, user)
    db.commit()
    db.refresh(user)
    return resp


def _unused_friend_code(db: Session) -> str:
    for _ in range(10):
        code = security.new_friend_code()
        if db.scalar(select(User.id).where(User.friend_code == code)) is None:
            return code
    raise RuntimeError("could not generate a unique friend code")


def login(db: Session, email: str, password: str) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == email.lower()))
    ok = security.verify_password(password, user.password_hash if user else None)
    if user is None or not ok or not user.is_registered or user.deleted_at is not None:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
    resp = _auth_response(db, user)
    db.commit()
    return resp


def _revoke_all(db: Session, user_id, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="reuse_detected")
    )
    db.commit()


def refresh(db: Session, raw_token: str) -> TokenPair:
    invalid = ApiError(401, "TOKEN_INVALID", "Session expired, please log in again")
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(raw_token))
    )
    if row is None:
        raise invalid
    now = _utcnow()
    if row.revoked_at is not None:
        # Only replaying a rotated token is theft; logout / reuse_detected / password_reset tokens just fail.
        if row.revoked_reason == "rotated":
            _revoke_all(db, row.user_id, now)
        raise invalid
    if _as_utc(row.expires_at) <= now:
        raise invalid
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise invalid
    # Atomic claim: only one concurrent request can flip revoked_at from NULL; a loser is token reuse.
    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="rotated")
    )
    if claimed.rowcount != 1:
        db.rollback()
        _revoke_all(db, row.user_id, now)
        raise invalid
    pair = _issue_tokens(db, user)
    db.commit()
    return pair


def logout(db: Session, user: User, raw_token: str) -> None:
    """Revoke the presented refresh token if it is this user's and still live. Always succeeds (idempotent)."""
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == security.hash_refresh_token(raw_token),
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow(), revoked_reason="logout")
    )
    db.commit()
