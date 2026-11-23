import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class Export(Base):
    """data_model `exports` (F-45). `purge_at` = created_at + 24 h; the API's `expires_at` is the signed-URL expiry and
    is computed on each read."""

    __tablename__ = "exports"
    __table_args__ = (
        CheckConstraint("scope IN ('group', 'friend')", name="ck_exports_scope"),
        CheckConstraint("format IN ('csv')", name="ck_exports_format"),
        CheckConstraint("status IN ('pending', 'ready', 'failed')", name="ck_exports_status"),
        Index("ix_exports_requested_by", "requested_by"),
        Index("ix_exports_purge_at", "purge_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("groups.id"), nullable=True)
    friend_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    format: Mapped[str] = mapped_column(Text, nullable=False, default="csv", server_default="csv")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default="pending")
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
