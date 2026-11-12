from sqlalchemy import Boolean, CHAR, SmallInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    exponent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
