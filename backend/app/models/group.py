import uuid
from datetime import date, datetime

from sqlalchemy import (CHAR, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger,
                        Text, func, text, true)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        # ck_groups_name_length (char_length) lives in the migration only; SQLite test DBs have no char_length().
        CheckConstraint("group_type IN ('home', 'trip', 'couple', 'other')", name="ck_groups_type"),
        CheckConstraint("trip_end_date IS NULL OR trip_start_date IS NULL OR trip_end_date >= trip_start_date",
                        name="ck_groups_trip_dates"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    group_type: Mapped[str] = mapped_column(Text, nullable=False)
    simplify_debts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    default_currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    trip_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    trip_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    whiteboard: Mapped[str | None] = mapped_column(Text, nullable=True)
    whiteboard_updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'admin')", name="ck_group_members_role"),
        Index("ix_group_members_user_group_active", "user_id", "group_id",
              postgresql_where=text("left_at IS NULL"), sqlite_where=text("left_at IS NULL")),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="member")
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
