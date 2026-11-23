import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, SmallInteger, Text, func, text, true
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class RecurringRule(Base):
    """data_model `recurring_rules` (F-40). The template expense is the first occurrence; its payers and splits are the
    template. `last_reminded_for` is the occurrence date a reminder was last queued for (dedupe for the scheduler)."""

    __tablename__ = "recurring_rules"
    __table_args__ = (
        CheckConstraint("interval IN ('weekly', 'fortnightly', 'monthly', 'yearly')", name="ck_recurring_rules_interval"),
        CheckConstraint("reminder_days_before IS NULL OR (reminder_days_before BETWEEN 0 AND 7)",
                        name="ck_recurring_rules_reminder_days"),
        Index("ix_recurring_rules_next_active", "next_occurrence_date",
              postgresql_where=text("active"), sqlite_where=text("active")),
        Index("uq_recurring_rules_template", "template_expense_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_expense_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("expenses.id"), nullable=False)
    interval: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    reminder_days_before: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    last_reminded_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    time_zone: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
