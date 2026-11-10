import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class Friendship(Base):
    """One row per pair; user_id is always the smaller uuid (check user_id < friend_id)."""

    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("user_id < friend_id", name="ck_friendships_ordered"),
        CheckConstraint("status IN ('active', 'removed', 'blocked')", name="ck_friendships_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    friend_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
