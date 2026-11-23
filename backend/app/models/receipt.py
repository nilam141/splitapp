import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base
from app.models.user import JsonType


class Receipt(Base):
    """data_model `receipts`: at most one per expense (MVP), so a re-upload replaces the row."""

    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("content_type IN ('image/jpeg', 'image/png')", name="ck_receipts_content_type"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_receipts_size"),
        Index("uq_receipts_expense", "expense_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("expenses.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    ocr_payload: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
