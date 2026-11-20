"""Per-group serialisation of leave/remove and expense writes (SELECT ... FOR UPDATE on the group row).

PostgreSQL only (SQLite has no row locks and a single writer). Each test holds the group lock in one session, plays the
"other half" of the race uncommitted, starts the competing HTTP request in a thread, asserts that it is BLOCKED (it does
not finish while the lock is held), then commits and asserts the competing request saw the committed state. Without the
lock the competing request would finish at once on its own snapshot: the leave would return 204 with a non-zero balance,
and the expense would return 201 naming a member who has left.
"""
import threading
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.models import Expense, ExpensePayer, ExpenseSplit, GroupMember
from app.services_groups import lock_group
from tests.conftest import PG_URL
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user

pytestmark = pytest.mark.skipif(not PG_URL, reason="needs PostgreSQL (TEST_DATABASE_URL)")


def _run(fn):
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("r", fn()), daemon=True)
    t.start()
    return t, box


def test_leave_waits_for_an_in_flight_expense_and_then_sees_the_balance(client, engine):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    x = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        lock_group(x, uuid.UUID(gid))
        eid = uuid.uuid4()
        x.add(Expense(id=eid, group_id=uuid.UUID(gid), description="Late", total_amount_minor=1000, currency="INR",
                      category_id=1, expense_date=date(2026, 11, 5), split_type="equal",
                      created_by=uuid.UUID(uid(a)), version=1))
        x.flush()
        x.add(ExpensePayer(expense_id=eid, user_id=uuid.UUID(uid(a)), paid_amount_minor=1000))
        x.add_all([ExpenseSplit(expense_id=eid, user_id=uuid.UUID(uid(a)), owed_amount_minor=500, sort_index=0),
                   ExpenseSplit(expense_id=eid, user_id=uuid.UUID(uid(b)), owed_amount_minor=500, sort_index=1)])
        x.flush()  # uncommitted: Ravi now owes 500, invisible to other sessions

        t, box = _run(lambda: client.delete(f"/groups/{gid}/members/me", headers=h(b)))
        t.join(1.0)
        assert t.is_alive(), "the leave did not wait for the group lock"
        x.commit()
        t.join(10)
        assert not t.is_alive()
        r = box["r"]
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "OUTSTANDING_BALANCE"
    finally:
        x.close()


def test_expense_waits_for_an_in_flight_leave_and_then_rejects_the_leaver(client, engine):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    x = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        lock_group(x, uuid.UUID(gid))
        m = x.get(GroupMember, (uuid.UUID(gid), uuid.UUID(uid(b))))
        m.left_at = datetime.now(timezone.utc)
        x.flush()  # uncommitted leave (balance was zero when it was checked)

        t, box = _run(lambda: client.post(f"/groups/{gid}/expenses", json=equal_body(a, [a, b]), headers=h(a)))
        t.join(1.0)
        assert t.is_alive(), "the expense did not wait for the group lock"
        x.commit()
        t.join(10)
        assert not t.is_alive()
        r = box["r"]
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "PARTICIPANT_NOT_MEMBER"
    finally:
        x.close()


def test_leave_waits_for_an_in_flight_delete_and_then_sees_the_new_balance(client, engine):
    """B owes 500 on X and paid 500 on Y (net 0). Deleting X makes B +500; a leave that already read 0 must not win."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    x_exp = create_group_expense(client, a, gid, equal_body(a, [a, b], total=1000, description="X"))
    create_group_expense(client, b, gid, equal_body(b, [a, b], total=1000, description="Y"))
    x = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        lock_group(x, uuid.UUID(gid))
        x.execute(update(Expense).where(Expense.id == uuid.UUID(x_exp["id"]))
                  .values(deleted_at=datetime.now(timezone.utc), deleted_by=uuid.UUID(uid(a))))
        x.flush()  # uncommitted delete

        t, box = _run(lambda: client.delete(f"/groups/{gid}/members/me", headers=h(b)))
        t.join(1.0)
        assert t.is_alive(), "the leave did not wait for the group lock"
        x.commit()
        t.join(10)
        assert not t.is_alive()
        r = box["r"]
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "OUTSTANDING_BALANCE"
    finally:
        x.close()


def test_delete_expense_waits_for_an_in_flight_leave(client, engine):
    """The service's own delete takes the lock: with the lock held elsewhere the DELETE request blocks."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = create_group_expense(client, a, gid, equal_body(a, [a], total=1000))
    x = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        lock_group(x, uuid.UUID(gid))
        t, box = _run(lambda: client.delete(f"/expenses/{e['id']}", headers=h(a)))
        t.join(1.0)
        assert t.is_alive(), "the delete did not wait for the group lock"
        x.commit()
        t.join(10)
        assert box["r"].status_code == 200, box["r"].text
    finally:
        x.close()
