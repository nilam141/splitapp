import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class Subscription(Base):
    """data_model `subscriptions` (F-46). Written by purchase verification (endpoint Blocked, decision D-C)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'premium_monthly', 'premium_yearly')", name="ck_subscriptions_plan"),
        CheckConstraint("status IN ('active', 'grace', 'expired', 'cancelled')", name="ck_subscriptions_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="free", server_default="free")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default="active")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    store: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
