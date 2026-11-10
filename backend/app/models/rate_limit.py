import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base


class RateLimitEvent(Base):
    """One counted attempt (a failed login, or a password-reset request). `key_hash` is a SHA-256 of the
    case-folded email or the client IP, so the table holds no addresses."""
    __tablename__ = "rate_limit_events"
    __table_args__ = (Index("ix_rate_limit_events_scope_key_created", "scope", "key_hash", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(Text, nullable=False)  # login_email | login_ip | reset_email
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
