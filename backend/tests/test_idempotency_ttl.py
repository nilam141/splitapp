"""Reviewer fix: an Idempotency-Key reused after the 24h TTL is a fresh request (201, second expense), not a 500."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Expense, IdempotencyKey
from tests.expense_helpers import equal_body, h, make_group, user


def _setup(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    return a, b, make_group(client, a, [b])


def _count(db):
    return db.scalar(select(func.count()).select_from(Expense))


def test_reuse_after_ttl_creates_a_second_expense(client, db_session):
    a, b, gid = _setup(client)
    key = str(uuid.uuid4())
    hdr = {**h(a), "Idempotency-Key": key}
    payload = equal_body(a, [a, b])
    r1 = client.post(f"/groups/{gid}/expenses", json=payload, headers=hdr)
    assert r1.status_code == 201
    row = db_session.scalars(select(IdempotencyKey)).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    r2 = client.post(f"/groups/{gid}/expenses", json=payload, headers=hdr)
    assert r2.status_code == 201
    assert r2.json()["id"] != r1.json()["id"]
    assert _count(db_session) == 2
    # the new key row is live again: an immediate replay returns the second response
    r3 = client.post(f"/groups/{gid}/expenses", json=payload, headers=hdr)
    assert r3.status_code == 201 and r3.json() == r2.json()
    assert _count(db_session) == 2


def test_replay_within_ttl_returns_first_response(client, db_session):
    a, b, gid = _setup(client)
    key = str(uuid.uuid4())
    hdr = {**h(a), "Idempotency-Key": key}
    payload = equal_body(a, [a, b])
    r1 = client.post(f"/groups/{gid}/expenses", json=payload, headers=hdr)
    row = db_session.scalars(select(IdempotencyKey)).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=23)
    db_session.commit()
    r2 = client.post(f"/groups/{gid}/expenses", json=payload, headers=hdr)
    assert r1.status_code == r2.status_code == 201 and r1.json() == r2.json()
    assert _count(db_session) == 1
