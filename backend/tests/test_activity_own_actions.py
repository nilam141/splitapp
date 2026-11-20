"""S5-Q-4: business_rules vector 49b (owner decision 2026-11-19): a user's own actions are never unread for them.

Written before S5-B-5. The backend still counts the actor's own entry (the actor is a recipient), so the "A's count stays 0"
and "A's item is_unread = false" assertions fail; the "B's count goes up" and "my_effect present" assertions already
hold. Both users' read mark is set to T0 (past) with the feed wiped, so every later event is newer than the mark.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, update

from app.models import ActivityLog, ActivityRecipient, User

from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user
from tests.settlement_helpers import pay

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def feed_all(client, who, **params):
    items, cursor, last = [], None, None
    for _ in range(20):
        q = dict(params, limit=3, **({"cursor": cursor} if cursor else {}))
        r = client.get("/activity", params=q, headers=h(who))
        assert r.status_code == 200, f"GET /activity -> {r.status_code}: {r.text}"
        body = r.json()
        counts = body["unread_count"]
        assert last is None or counts == last, "unread_count must be the same on every page"
        last = counts
        items += body["items"]
        cursor = body["next_cursor"]
        if not cursor:
            return items, last
    raise AssertionError("cursor never ended")


def count(client, who):
    r = client.get("/activity", params={"limit": 1}, headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()["unread_count"]


def unread_items(client, who):
    return [i for i in feed_all(client, who)[0] if i["is_unread"]]


@pytest.fixture()
def w(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    db_session.execute(delete(ActivityRecipient))
    db_session.execute(delete(ActivityLog))
    db_session.execute(update(User).where(User.id.in_([uuid.UUID(uid(a)), uuid.UUID(uid(b))]))
                       .values(activity_last_read_at=T0))
    db_session.commit()
    assert count(client, a) == 0 and count(client, b) == 0
    return {"a": a, "b": b, "gid": gid}


def top(client, who):
    items, _ = feed_all(client, who)
    return items[0]


def assert_own_read_other_unread(client, w, action):
    """The newest entry is by A: read for A (with my_effect), unread for B."""
    a, b = w["a"], w["b"]
    mine, theirs = top(client, a), top(client, b)
    assert mine["action"] == action and theirs["action"] == action and mine["id"] == theirs["id"]
    assert mine["actor"]["id"] == uid(a)
    assert mine["is_unread"] is False, "own action must never be unread for the actor"
    assert theirs["is_unread"] is True
    return mine, theirs


def test_vector_49b_own_expense_is_read_for_a_unread_for_b_then_b_acts(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=10000))
    mine, theirs = assert_own_read_other_unread(client, w, "expense.created")
    assert count(client, a) == 0 and count(client, b) == 1
    assert mine["my_effect"] == [{"amount_minor": 5000, "currency": "INR"}], "the real effect for A, not null or empty"
    assert theirs["my_effect"] == [{"amount_minor": -5000, "currency": "INR"}]
    assert [i["id"] for i in unread_items(client, b)] == [theirs["id"]] and unread_items(client, a) == []
    # B now adds an expense: B's own entry is read for B, so B stays at 1; A's becomes 1
    create_group_expense(client, b, gid, equal_body(b, [a, b], total=2000, description="Taxi"))
    assert count(client, b) == 1 and count(client, a) == 1
    b_top, a_top = top(client, b), top(client, a)
    assert b_top["actor"]["id"] == uid(b) and b_top["is_unread"] is False and b_top["my_effect"]
    assert a_top["id"] == b_top["id"] and a_top["is_unread"] is True


def test_vector_49b_edit_delete_restore_by_a(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e = create_group_expense(client, a, gid, equal_body(a, [a, b], total=10000))
    steps = [
        ("expense.updated", lambda: client.patch(f"/expenses/{e['id']}", headers=h(a), json={
            "version": 1, "total": {"amount_minor": 12000, "currency": "INR"}})),
        ("expense.deleted", lambda: client.delete(f"/expenses/{e['id']}", headers=h(a))),
        ("expense.restored", lambda: client.post(f"/expenses/{e['id']}/restore", headers=h(a))),
    ]
    for n, (action, do) in enumerate(steps, start=2):
        r = do()
        assert r.status_code == 200, r.text
        mine, theirs = assert_own_read_other_unread(client, w, action)
        assert mine["my_effect"], f"{action}: A's own item keeps its real my_effect"
        assert count(client, a) == 0, action
        assert count(client, b) == n, action          # create + this many later events, all unread for B
    items_a, _ = feed_all(client, a)
    assert len(items_a) == 4 and not any(i["is_unread"] for i in items_a)


def test_vector_49b_settlement_actions_by_a(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    s = pay(client, a, b, a, 2000, group_id=gid)                       # A records B paying A
    mine, theirs = assert_own_read_other_unread(client, w, "settlement.created")
    assert mine["my_effect"] and theirs["my_effect"]
    steps = [("settlement.updated", lambda: client.patch(f"/settlements/{s['id']}", headers=h(a), json={
                 "version": 1, "amount": {"amount_minor": 2500, "currency": "INR"}})),
             ("settlement.deleted", lambda: client.delete(f"/settlements/{s['id']}", headers=h(a))),
             ("settlement.restored", lambda: client.post(f"/settlements/{s['id']}/restore", headers=h(a)))]
    for n, (action, do) in enumerate(steps, start=2):
        assert do().status_code == 200
        assert_own_read_other_unread(client, w, action)
        assert count(client, a) == 0 and count(client, b) == n, action


def test_vector_49b_comment_by_a(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e = create_group_expense(client, b, gid, equal_body(b, [a, b]))      # unread for A (B's own), read for B
    assert count(client, a) == 1 and count(client, b) == 0
    assert client.post(f"/expenses/{e['id']}/comments", json={"body": "hi"}, headers=h(a)).status_code == 201
    mine, theirs = assert_own_read_other_unread(client, w, "comment.created")
    assert count(client, a) == 1 and count(client, b) == 1                # A's comment is not unread for A


def test_vector_49b_system_entry_is_unread_for_everyone(client, w, db_session):
    a, b, gid = w["a"], w["b"], w["gid"]
    act_id = uuid.uuid4()
    db_session.add(ActivityLog(id=act_id, actor_id=None, action="expense.created", entity_type="expense",
                               entity_id=uuid.uuid4(), group_id=uuid.UUID(gid),
                               payload={"description": "Rent", "total": {"amount_minor": 100, "currency": "INR"}},
                               created_at=datetime.now(timezone.utc)))
    db_session.flush()
    db_session.add_all(ActivityRecipient(activity_id=act_id, user_id=uuid.UUID(uid(u)), balance_effect=None)
                      for u in (a, b))
    db_session.commit()
    for who in (a, b):
        assert count(client, who) == 1
        item = top(client, who)
        assert item["id"] == str(act_id) and item["is_unread"] is True and item["actor"] is None


def test_vector_49b_unread_count_equals_unread_items_over_a_mixed_feed(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))
    create_group_expense(client, b, gid, equal_body(b, [a, b], description="Taxi"))
    pay(client, b, b, a, 500, group_id=gid)
    client.patch(f"/expenses/{e['id']}", json={"version": 1, "description": "Renamed"}, headers=h(a))
    client.post(f"/expenses/{e['id']}/comments", json={"body": "x"}, headers=h(b))
    for who in (a, b):
        items, counted = feed_all(client, who)
        assert counted == sum(1 for i in items if i["is_unread"])
        assert len(items) == 5
    # per user: the entries by the other user are unread, own are not
    for who, other in ((a, b), (b, a)):
        items, counted = feed_all(client, who)
        assert {i["actor"]["id"] for i in items if i["is_unread"]} <= {uid(other)}
        assert all(not i["is_unread"] for i in items if i["actor"]["id"] == uid(who))
        assert counted == sum(1 for i in items if i["actor"]["id"] == uid(other))
    # group_id filter does not change the count, and the own entries are still listed
    items, counted = feed_all(client, a, group_id=gid)
    assert counted == count(client, a) and any(i["actor"]["id"] == uid(a) for i in items)


def test_vector_49b_mark_read_semantics_unchanged(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    create_group_expense(client, a, gid, equal_body(a, [a, b]))
    create_group_expense(client, b, gid, equal_body(b, [a, b], description="Taxi"))
    assert count(client, a) == 1 and count(client, b) == 1
    assert client.post("/activity/read", headers=h(a)).status_code == 204
    assert count(client, a) == 0 and count(client, b) == 1               # B's count is independent
    assert not any(i["is_unread"] for i in feed_all(client, a)[0])
    time.sleep(1.1)                                                      # later than the read mark (second resolution)
    create_group_expense(client, a, gid, equal_body(a, [a, b], description="Own after read"))
    assert count(client, a) == 0                                         # own action: still not unread
    create_group_expense(client, b, gid, equal_body(b, [a, b], description="B after read"))
    assert count(client, a) == 1 and count(client, b) == 2
