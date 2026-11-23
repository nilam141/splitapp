"""Shared helpers for the Slice 3 expense API tests (S3-Q-4, S3-Q-5). Test code only."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from tests.test_auth import reg


def h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def uid(d):
    return d["user"]["id"]


def user(client, name):
    return reg(client, email=f"{name.lower()}@example.com", name=name).json()


def make_group(client, owner, members, name="G"):
    r = client.post("/groups", json={"name": name, "member_user_ids": [uid(m) for m in members]}, headers=h(owner))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def equal_body(payer, participants, total=10000, description="Dinner", date="2026-11-05", currency="INR", **extra):
    return {"description": description, "total": {"amount_minor": total, "currency": currency},
            "expense_date": date, "payers": [{"user_id": uid(payer), "paid_amount_minor": total}],
            "split": {"type": "equal", "entries": [{"user_id": uid(p)} for p in participants]}, **extra}


def create_group_expense(client, who, gid, body):
    """POST /groups/{id}/expenses; the assertion message says which slice task is missing when it is not there."""
    r = client.post(f"/groups/{gid}/expenses", json=body, headers=h(who))
    assert r.status_code == 201, f"setup POST /groups/{{id}}/expenses -> {r.status_code} (needs S3-B-3): {r.text}"
    return r.json()


def create_expense(client, who, body):
    r = client.post("/expenses", json=body, headers=h(who))
    assert r.status_code == 201, f"setup POST /expenses -> {r.status_code} (needs S3-B-3): {r.text}"
    return r.json()


def expenses_table():
    from app.db import Base
    return Base.metadata.tables["expenses"]  # created by S3-B-2; KeyError before that, after the setup POST failed


def set_created_at(db, expense_id, when: datetime):
    t = expenses_table()
    db.execute(update(t).where(t.c.id == uuid.UUID(expense_id)).values(created_at=when.astimezone(timezone.utc)))
    db.commit()
