"""Pydantic schemas mirroring docs/openapi.yaml (v0.1.1)."""
import uuid
from datetime import date, datetime
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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


def _check_tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("unknown IANA time zone")
    return v


PHONE_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None = None
    slug: str
    name: str
    icon: str
    children: list["CategoryOut"] = []


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class NotificationPrefsUpdate(BaseModel):
    """Partial: omitted keys keep their value (merged key by key)."""

    model_config = ConfigDict(extra="forbid")

    expense_added: bool | None = None
    expense_updated: bool | None = None
    comment_added: bool | None = None
    added_to_group: bool | None = None
    removed_from_group: bool | None = None
    group_updated: bool | None = None
    friend_added: bool | None = None
    friend_removed: bool | None = None
    payment_recorded: bool | None = None
    reminder: bool | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "NotificationPrefsUpdate":
        for key in self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{key} must be a boolean")
        return self


class UserUpdate(BaseModel):
    """Partial update; only fields present in the body are applied. Only phone_e164 may be set to null."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=254)
    phone_e164: str | None = Field(default=None, pattern=PHONE_RE.pattern)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    time_zone: str | None = None
    notification_prefs: NotificationPrefsUpdate | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "UserUpdate":
        for key in self.model_fields_set - {"phone_e164"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        if self.time_zone is not None:
            _check_tz(self.time_zone)
        return self


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None = None
    avatar_url: str | None = None
    is_registered: bool


class BalanceLine(BaseModel):
    amount_minor: int
    currency: str


class ScopedBalance(BaseModel):
    scope: Literal["group", "non_group"]
    group_id: uuid.UUID | None = None
    group_name: str | None = None
    balances: list[BalanceLine]


class Friend(BaseModel):
    user: UserPublic
    balances: list[BalanceLine] = []
    breakdown: list[ScopedBalance] = []
    settled_up_since: datetime | None = None


class FriendList(BaseModel):
    items: list[Friend]


class FriendCreate(BaseModel):
    email: EmailStr | None = None
    phone_e164: str | None = Field(default=None, pattern=PHONE_RE.pattern)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    friend_code: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "FriendCreate":
        given = [k for k in ("email", "phone_e164", "friend_code") if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError("provide exactly one of email, phone_e164 or friend_code")
        return self


class FriendCreated(BaseModel):
    friend: Friend
    is_new_user: bool


# ---------- groups ----------
GroupType = Literal["home", "trip", "couple", "other"]


class GroupMemberOut(BaseModel):
    user: UserPublic
    joined_at: datetime
    left_at: datetime | None = None
    balances: list[BalanceLine] = []


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    group_type: GroupType
    simplify_debts: bool
    default_currency: str
    avatar_url: str | None = None
    trip_start_date: date | None = None
    trip_end_date: date | None = None
    whiteboard: str | None = None
    members: list[GroupMemberOut]
    my_balances: list[BalanceLine] = []
    version: int
    created_by: uuid.UUID
    created_at: datetime
    deleted_at: datetime | None = None


class GroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    group_type: GroupType
    avatar_url: str | None = None
    member_count: int
    my_balances: list[BalanceLine] = []
    settled_up_since: datetime | None = None
    updated_at: datetime


class GroupList(BaseModel):
    items: list[GroupSummary]
    non_group_balances: list[BalanceLine] = []


class NewMember(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone_e164: str | None = Field(default=None, pattern=PHONE_RE.pattern)


# The 200-member cap is enforced in the service (422 GROUP_TOO_LARGE), so these lists carry no schema maxItems.
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    group_type: GroupType = "other"
    simplify_debts: bool = True
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    trip_start_date: date | None = None
    trip_end_date: date | None = None
    member_user_ids: list[uuid.UUID] = []
    new_members: list[NewMember] = []


class GroupUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=100)
    group_type: GroupType | None = None
    simplify_debts: bool | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    trip_start_date: date | None = None
    trip_end_date: date | None = None
    whiteboard: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def _no_nulls(self) -> "GroupUpdate":
        for key in self.model_fields_set - {"trip_start_date", "trip_end_date", "whiteboard"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class MembersAdd(BaseModel):
    user_ids: list[uuid.UUID] = []
    new_members: list[NewMember] = []


# ---------- balances ----------
class Transfer(BaseModel):
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    amount_minor: int
    currency: str


class GroupBalanceMember(BaseModel):
    user_id: uuid.UUID
    balances: list[BalanceLine]


class GroupBalances(BaseModel):
    group_id: uuid.UUID
    simplified: bool
    members: list[GroupBalanceMember]
    transfers: list[Transfer]


class OverallFriend(BaseModel):
    user_id: uuid.UUID
    balances: list[BalanceLine]


class OverallBalances(BaseModel):
    you_are_owed: list[BalanceLine]
    you_owe: list[BalanceLine]
    by_friend: list[OverallFriend]
