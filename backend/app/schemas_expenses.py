"""Pydantic schemas for expenses, the group timeline and comments, mirroring docs/openapi.yaml (0.2.0).

Money inputs are StrictInt: a JSON float or string for an amount is a 422, never silently converted."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

from app.schemas import UserPublic

SplitTypeName = Literal["equal", "exact", "percent", "shares", "adjustment"]


class MoneyIn(BaseModel):
    amount_minor: StrictInt
    currency: str


class MoneyOut(BaseModel):
    amount_minor: int
    currency: str


class PayerInput(BaseModel):
    user_id: uuid.UUID
    paid_amount_minor: StrictInt = Field(ge=1)


class SplitEntryInput(BaseModel):
    user_id: uuid.UUID
    value: StrictInt | None = Field(default=None, ge=0)


class SplitInput(BaseModel):
    type: SplitTypeName
    entries: list[SplitEntryInput] = Field(min_length=1)


class RecurrenceInput(BaseModel):
    interval: Literal["weekly", "fortnightly", "monthly", "yearly"]
    reminder_days_before: int | None = Field(default=None, ge=0, le=7)


def _clean_description(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("description must not be blank")
    return v


class ExpenseCreate(BaseModel):
    group_id: uuid.UUID | None = None
    description: str = Field(min_length=1, max_length=200)
    total: MoneyIn
    category_id: int = 1
    expense_date: date
    notes: str | None = Field(default=None, max_length=2000)
    payers: list[PayerInput] = Field(min_length=1)
    split: SplitInput
    recurrence: RecurrenceInput | None = None

    _desc = field_validator("description")(_clean_description)


class ExpenseUpdate(BaseModel):
    """Partial update; only fields present in the body are applied. Only `notes` may be null."""

    version: StrictInt
    description: str | None = Field(default=None, min_length=1, max_length=200)
    total: MoneyIn | None = None
    category_id: int | None = None
    expense_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    payers: list[PayerInput] | None = None
    split: SplitInput | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "ExpenseUpdate":
        for key in self.model_fields_set - {"notes"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        if self.description is not None:
            self.description = _clean_description(self.description)
        return self


class ExpensePayerOut(BaseModel):
    user_id: uuid.UUID
    paid_amount_minor: int


class ExpenseSplitOut(BaseModel):
    user_id: uuid.UUID
    owed_amount_minor: int
    input_value: int | None = None


class ExpenseOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID | None = None
    description: str
    total: MoneyOut
    category_id: int
    expense_date: date
    notes: str | None = None
    split_type: SplitTypeName
    payers: list[ExpensePayerOut]
    splits: list[ExpenseSplitOut]
    my_net: MoneyOut
    receipt_url: str | None = None
    recurring_rule_id: uuid.UUID | None = None
    comment_count: int
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None
    version: int


class ExpensePage(BaseModel):
    items: list[ExpenseOut]
    next_cursor: str | None = None


class TimelineExpense(BaseModel):
    kind: Literal["expense"] = "expense"
    date: date
    expense: ExpenseOut


class TimelinePage(BaseModel):
    # Settlement items join the union in S5-B-4.
    items: list[TimelineExpense]
    next_cursor: str | None = None


class CommentOut(BaseModel):
    id: uuid.UUID
    kind: Literal["user", "system"]
    user: UserPublic | None = None
    body: str
    created_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("body must not be blank")
        return v


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: str | None = None
