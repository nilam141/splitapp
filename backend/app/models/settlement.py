import uuid
from datetime import date, datetime

from sqlalchemy import (CHAR, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text,
                        UniqueConstraint, desc, func, text)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        # char_length(note) <= 500 lives in the migration only; SQLite test DBs have no char_length().
        CheckConstraint("amount_minor > 0 AND amount_minor <= 9999999999", name="ck_settlements_amount_range"),
        CheckConstraint("from_user_id <> to_user_id", name="ck_settlements_distinct_parties"),
        CheckConstraint("method IN ('cash')", name="ck_settlements_method"),
        UniqueConstraint("created_by", "idempotency_key", name="uq_settlements_created_by_idempotency_key"),
        Index("ix_settlements_group_date_live", "group_id", desc("settled_on"), desc("created_at"), desc("id"),
              postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL")),
        Index("ix_settlements_group_id", "group_id"),
        Index("ix_settlements_from_user_id", "from_user_id"),
        Index("ix_settlements_to_user_id", "to_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("groups.id"), nullable=True)
    from_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=False)
    settled_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default="cash", default="cash")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
