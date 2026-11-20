"""Shared helpers for the Slice 5 settlement and activity tests (S5-Q-1, S5-Q-3). Test code only."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from tests.expense_helpers import h, uid


def sbody(frm, to, amount, currency="INR", group_id=None, settled_on="2026-11-05", **extra):
    return {"group_id": group_id, "from_user_id": uid(frm), "to_user_id": uid(to),
            "amount": {"amount_minor": amount, "currency": currency}, "settled_on": settled_on, **extra}


def pay(client, who, frm, to, amount, currency="INR", group_id=None, **extra):
    """POST /settlements; the assertion names the status so a missing endpoint reads as 'needs S5-B-2'."""
    r = client.post("/settlements", json=sbody(frm, to, amount, currency, group_id, **extra), headers=h(who))
    assert r.status_code == 201, f"setup POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    return r.json()


def befriend(client, who, other):
    r = client.post("/friends", json={"email": other["user"]["email"]}, headers=h(who))
    assert r.status_code in (201, 200), r.text


def settlements_table():
    from app.db import Base
    return Base.metadata.tables["settlements"]  # created by S5-B-1; KeyError before that


def set_settlement_created_at(db, settlement_id, when: datetime):
    t = settlements_table()
    db.execute(update(t).where(t.c.id == uuid.UUID(settlement_id)).values(created_at=when.astimezone(timezone.utc)))
    db.commit()


def settlement_deleted_at(db, settlement_id):
    t = settlements_table()
    db.expire_all()
    return db.execute(select(t.c.deleted_at).where(t.c.id == uuid.UUID(settlement_id))).scalar_one()
