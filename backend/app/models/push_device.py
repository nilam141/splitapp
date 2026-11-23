import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class PushDevice(Base):
    """data_model `push_devices`. No API registers devices yet (endpoint Blocked, decision D-C); the sender reads them."""

    __tablename__ = "push_devices"
    __table_args__ = (
        CheckConstraint("platform IN ('android')", name="ck_push_devices_platform"),
        Index("uq_push_devices_token", "token", unique=True),
        Index("ix_push_devices_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="android", server_default="android")
    token: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
