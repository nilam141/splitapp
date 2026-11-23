"""Pydantic schemas for settlements and the activity feed, mirroring docs/openapi.yaml (0.2.0).

Money inputs are StrictInt: a JSON float or string for an amount is a 422, never silently converted."""
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictInt

from app.schemas import BalanceLine, UserPublic
from app.schemas_expenses import MoneyIn, MoneyOut, TimelineExpense


class SettlementCreate(BaseModel):
    group_id: uuid.UUID | None = None
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    amount: MoneyIn
    settled_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class SettlementUpdate(BaseModel):
    """Partial update; only fields present in the body are applied. Only `note` may be null."""

    version: StrictInt
    amount: MoneyIn | None = None
    settled_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class SettleAllRequest(BaseModel):
    friend_user_id: uuid.UUID
    currency: str | None = None


class SettlementOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID | None = None
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    amount: MoneyOut
    settled_on: date
    note: str | None = None
    batch_id: uuid.UUID | None = None
    created_by: uuid.UUID
    created_at: datetime
    deleted_at: datetime | None = None
    version: int


class SettlementPage(BaseModel):
    items: list[SettlementOut]
    next_cursor: str | None = None


class SettleAllOut(BaseModel):
    batch_id: uuid.UUID
    items: list[SettlementOut]


class TimelineSettlement(BaseModel):
    kind: Literal["settlement"] = "settlement"
    date: date
    settlement: SettlementOut


TimelineItem = Annotated[TimelineExpense | TimelineSettlement, Field(discriminator="kind")]


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    next_cursor: str | None = None


ActivityAction = Literal[
    "expense.created", "expense.updated", "expense.deleted", "expense.restored", "settlement.created",
    "settlement.updated", "settlement.deleted", "settlement.restored", "comment.created", "group.created",
    "group.updated", "group.deleted", "group.restored", "group.member_added", "group.member_removed",
    "group.member_joined", "friend.added", "friend.removed", "group.currency_converted"]


class ActivityItem(BaseModel):
    id: uuid.UUID
    action: ActivityAction
    actor: UserPublic | None = None
    entity_type: Literal["expense", "settlement", "group", "friendship", "comment"]
    entity_id: uuid.UUID
    group_id: uuid.UUID | None = None
    summary: dict[str, Any] | None = None
    my_effect: list[BalanceLine] = []
    is_unread: bool
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    next_cursor: str | None = None
    unread_count: int = Field(ge=0)
