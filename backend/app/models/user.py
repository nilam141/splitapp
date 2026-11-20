import uuid
from datetime import datetime, timezone

from sqlalchemy import CHAR, JSON, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db import Base

# citext on PostgreSQL (case-insensitive unique email); plain string elsewhere (tests on SQLite
# normalise to lower case in the service layer as well).
EmailType = String(254).with_variant(CITEXT(), "postgresql")
JsonType = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email", "email", unique=True, postgresql_where=text("email IS NOT NULL"),
              sqlite_where=text("email IS NOT NULL")),
        Index("uq_users_phone_e164", "phone_e164", unique=True, postgresql_where=text("phone_e164 IS NOT NULL"),
              sqlite_where=text("phone_e164 IS NOT NULL")),
        Index("uq_users_google_sub", "google_sub", unique=True, postgresql_where=text("google_sub IS NOT NULL"),
              sqlite_where=text("google_sub IS NOT NULL")),
        Index("uq_users_friend_code", "friend_code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(EmailType, nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_registered: Mapped[bool] = mapped_column(nullable=False, default=False)
    default_currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=False)
    time_zone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Kolkata")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en-IN")
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_prefs: Mapped[dict] = mapped_column(JsonType, nullable=False)
    activity_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    friend_code: Mapped[str] = mapped_column(String(16), nullable=False)
    google_sub: Mapped[str | None] = mapped_column(Text, nullable=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    merged_into: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Premium entitlement (S6-B-6): `plan` and `premium_until` on UserMe come from the subscription row.
    subscription = relationship("Subscription", uselist=False, lazy="joined", viewonly=True)

    def is_premium(self, now: datetime | None = None) -> bool:
        """Premium = a non-free plan with status active or grace whose period has not ended (null end = no expiry)."""
        sub = self.subscription
        if sub is None or sub.plan == "free" or sub.status not in ("active", "grace"):
            return False
        end = sub.current_period_end
        if end is None:
            return True
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return end > (now or datetime.now(timezone.utc))

    @property
    def plan(self) -> str:
        return "premium" if self.is_premium() else "free"

    @property
    def premium_until(self) -> datetime | None:
        return self.subscription.current_period_end if self.is_premium() else None
