import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db import Base
from app.models.user import JsonType


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    key: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    method_path: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
