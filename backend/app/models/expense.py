import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (CHAR, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
                        SmallInteger, Text, UniqueConstraint, desc, func, text)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base

SPLIT_TYPES = ("equal", "exact", "percent", "shares", "adjustment", "itemized")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        # char_length checks (description, notes) live in the migration only; SQLite test DBs have no char_length().
        CheckConstraint("total_amount_minor > 0 AND total_amount_minor <= 9999999999", name="ck_expenses_total_range"),
        CheckConstraint("split_type IN ('equal', 'exact', 'percent', 'shares', 'adjustment', 'itemized')",
                        name="ck_expenses_split_type"),
        UniqueConstraint("created_by", "idempotency_key", name="uq_expenses_created_by_idempotency_key"),
        UniqueConstraint("recurring_rule_id", "occurrence_date", name="uq_expenses_rule_occurrence"),
        Index("ix_expenses_group_date_live", "group_id", desc("expense_date"), desc("created_at"), desc("id"),
              postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("groups.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=False)
    category_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("categories.id"), nullable=False,
                                             server_default="1", default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    split_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    # FK to recurring_rules is added by the recurring migration (S6-B-1); the column exists from here on.
    recurring_rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set by the (later) currency conversion. fx_rate is a rate, not money.
    fx_original_amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fx_original_currency: Mapped[str | None] = mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExpensePayer(Base):
    __tablename__ = "expense_payers"
    __table_args__ = (
        CheckConstraint("paid_amount_minor > 0", name="ck_expense_payers_positive"),
        Index("ix_expense_payers_user_id", "user_id"),
    )

    expense_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("expenses.id", ondelete="CASCADE"),
                                                  primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    paid_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (
        CheckConstraint("owed_amount_minor >= 0", name="ck_expense_splits_non_negative"),
        Index("ix_expense_splits_user_id", "user_id"),
    )

    expense_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("expenses.id", ondelete="CASCADE"),
                                                  primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    owed_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sort_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("kind IN ('user', 'system')", name="ck_comments_kind"),
        CheckConstraint("(expense_id IS NOT NULL) <> (settlement_id IS NOT NULL)", name="ck_comments_one_target"),
        CheckConstraint("(kind = 'system') = (user_id IS NULL)", name="ck_comments_system_has_no_user"),
        Index("ix_comments_expense_created", "expense_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("expenses.id"), nullable=True)
    # FK to settlements is added by the settlements migration (S5-B-1); comments on settlements are reserved.
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
