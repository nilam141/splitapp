"""Sliding-window rate limits (business_rules 11.2). Counted attempts live in `rate_limit_events` (no new
infrastructure). Time comes from `datetime.now(timezone.utc)`. `check` raises 429 without recording anything, so
limited calls are not counted; `record` is called only for a counted attempt."""
import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import RateLimitEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _retry_after(db: Session, scope: str, key: str, limit: int, window: int, now: datetime) -> int | None:
    """None if under the limit, else whole seconds until the oldest counted attempt leaves the window."""
    cutoff = now - timedelta(seconds=window)
    count, oldest = db.execute(
        select(func.count(), func.min(RateLimitEvent.created_at)).where(
            RateLimitEvent.scope == scope, RateLimitEvent.key_hash == _hash(key), RateLimitEvent.created_at > cutoff)
    ).one()
    if count < limit or oldest is None:
        return None
    return max(1, math.ceil((_aware(oldest) + timedelta(seconds=window) - now).total_seconds()))


def _lock(db: Session, rules: list[tuple[str, str, int, int]]) -> None:
    """On PostgreSQL, take transaction-scoped advisory locks on every key (sorted, so no deadlocks) so that
    concurrent check -> record sequences for the same key serialise and cannot all pass together. The locks are
    released at commit/rollback/session close. No-op on other databases (SQLite has a single writer in tests)."""
    if db.get_bind().dialect.name != "postgresql":
        return
    keys = sorted({int.from_bytes(hashlib.sha256(f"{scope}:{key}".encode()).digest()[:8], "big", signed=True)
                   for scope, key, _, _ in rules})
    for k in keys:
        db.execute(select(func.pg_advisory_xact_lock(k)))


def check(db: Session, rules: list[tuple[str, str, int, int]]) -> None:
    """rules: (scope, key, max_attempts, window_seconds). Raises 429 RATE_LIMITED with the longest wait.
    The caller must record (and commit) in the same transaction for the lock to cover the whole sequence."""
    _lock(db, rules)
    now = _now()
    waits = [w for scope, key, limit, window in rules
             if (w := _retry_after(db, scope, key, limit, window, now)) is not None]
    if waits:
        wait = max(waits)
        raise ApiError(429, "RATE_LIMITED", "Too many attempts, try again later", {"retry_after_seconds": wait},
                       headers={"Retry-After": str(wait)})


def record(db: Session, scope: str, key: str, window: int) -> None:
    """Count one attempt and drop this key's attempts that are far outside the window. Caller commits."""
    now = _now()
    h = _hash(key)
    db.execute(delete(RateLimitEvent).where(
        RateLimitEvent.scope == scope, RateLimitEvent.key_hash == h,
        RateLimitEvent.created_at <= now - timedelta(seconds=window * 2)))
    db.add(RateLimitEvent(id=uuid.uuid4(), scope=scope, key_hash=h, created_at=now))
