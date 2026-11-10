"""Pydantic schemas mirroring docs/openapi.yaml (v0.1.1)."""
import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    default_currency: str = Field(default="INR", min_length=3, max_length=3)
    time_zone: str = "Asia/Kolkata"

    @field_validator("time_zone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("unknown IANA time zone")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class NotificationPrefs(BaseModel):
    expense_added: bool
    expense_updated: bool
    comment_added: bool
    added_to_group: bool
    removed_from_group: bool
    group_updated: bool
    friend_added: bool
    friend_removed: bool
    payment_recorded: bool
    reminder: bool


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    phone_e164: str | None = None
    default_currency: str
    time_zone: str
    avatar_url: str | None = None
    is_registered: bool
    plan: Literal["free", "premium"] = "free"
    premium_until: datetime | None = None
    friend_code: str
    notification_prefs: NotificationPrefs
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class AuthResponse(TokenPair):
    user: UserMe


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    symbol: str
    exponent: int
