import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base
from app.models.user import JsonType


class Notification(Base):
    """Outbox for push and email. Rows are written here and delivered by a sender (console/log until S6-B-3)."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("channel IN ('push', 'email')", name="ck_notifications_channel"),
        CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped_pref')", name="ck_notifications_status"),
        Index("ix_notifications_status_created", "status", "created_at"),
        Index("ix_notifications_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # FK added with activity_log (S2-B-6)
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
