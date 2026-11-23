"""Recurring-rule schemas mirroring docs/openapi.yaml (RecurringRule, RecurringCreate, RecurringUpdate, RecurringList)."""
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas_expenses import MoneyOut

Interval = Literal["weekly", "fortnightly", "monthly", "yearly"]


class RecurringRuleOut(BaseModel):
    id: uuid.UUID
    template_expense_id: uuid.UUID
    group_id: uuid.UUID | None = None
    description: str
    total: MoneyOut
    interval: Interval
    anchor_date: date
    next_occurrence_date: date
    reminder_days_before: int | None = None
    active: bool


class RecurringList(BaseModel):
    items: list[RecurringRuleOut]


class RecurringCreate(BaseModel):
    template_expense_id: uuid.UUID
    interval: Interval
    reminder_days_before: int | None = Field(default=None, ge=0, le=7)


class RecurringUpdate(BaseModel):
    interval: Interval | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=7)
    active: bool | None = None
