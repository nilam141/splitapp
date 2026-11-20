"""Premium gating (S6-B-6). `User.is_premium()` reads the subscription row. Gated: expense search, CSV export, receipt
upload. The Play purchase verification endpoint is Blocked (decision D-C); `grant` is what it will call."""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Subscription, User


def require_premium(user: User, feature: str) -> None:
    if not user.is_premium():
        raise ApiError(402, "PREMIUM_REQUIRED", "This feature requires premium", {"feature": feature})


def grant(db: Session, user_id: uuid.UUID, plan: str = "premium_monthly", status: str = "active",
          period_end: datetime | None = None, store: str | None = "google_play") -> Subscription:
    """Create or replace the user's subscription row (caller commits)."""
    sub = db.get(Subscription, user_id)
    if sub is None:
        sub = Subscription(user_id=user_id)
        db.add(sub)
    sub.plan, sub.status, sub.current_period_end, sub.store = plan, status, period_end, store
    db.flush()
    user = db.get(User, user_id)
    if user is not None:
        db.refresh(user)
    return sub
