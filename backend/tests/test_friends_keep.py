"""S2-Q-4: keep friends when a shared group ends (OQ-37a, business_rules 10.1a, vectors 52-60).

Written before S2-B-8. Today leave / remove / delete write no `friendships` row, so every test that expects a new row
fails on the first row-count or status assertion (an AssertionError on `friendships`, not an HTTP or setup error).
Tests that only assert "nothing is written" or that pass for other reasons are noted on the test.

Notes on test seams:
- Restore: `POST /groups/{id}/restore` is V2 and not implemented, so vector 58 restores through the database
  (`deleted_at = NULL`). Restore must not touch friendships, so this is the same observable state.
- Vector 55: the balance guard `member_balances` is stubbed to 0 until S4-B-3. The test seeds B's debt by patching
  that function (`app.services_groups.member_balances`); the patch still works after S4-B-3 only if that name stays.
  The real-balance variant (no stub) is `test_vector_55_with_real_debt_after_s4_b_3`, active since S4-Q-1.
- Activity: S2-B-6 already writes `group.member_removed` / `group.deleted` rows. The tests compare activity_log,
  activity_recipients and notifications before/after and require that only those rows appear.
"""
import uuid

import pytest
from sqlalchemy import func, select, update

from app.models import ActivityLog, ActivityRecipient, Friendship, Group, Notification
from app.schemas import BalanceLine

from tests.test_auth import reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def _uid(d):
    return d["user"]["id"]


def _user(client, name):
    return reg(client, email=f"{name.lower()}@example.com", name=name).json()


def _users_with_order(client, names, a_lt_b):
    """Register users until the first two have the wanted uuid order (user ids are random)."""
    for i in range(40):
        us = [reg(client, email=f"{n.lower()}{i}@example.com", name=n).json() for n in names]
        if (uuid.UUID(_uid(us[0])) < uuid.UUID(_uid(us[1]))) == a_lt_b:
            return us
    raise AssertionError("could not draw the wanted uuid order")


def _group(client, owner, members, name="G"):
    r = client.post("/groups", json={"name": name, "member_user_ids": [_uid(m) for m in members]}, headers=_h(owner))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _leave(client, who, gid):
    return client.delete(f"/groups/{gid}/members/me", headers=_h(who))


def _friend_ids(client, d):
    r = client.get("/friends", headers=_h(d))
    assert r.status_code == 200, r.text
    ids = [i["user"]["id"] for i in r.json()["items"]]
    assert len(ids) == len(set(ids)), "a friend must be listed once"
    return set(ids)


def _rows(db):
    """All friendship rows as {(user_id, friend_id): status}, ids as strings."""
    db.expire_all()
    out = {}
    for f in db.scalars(select(Friendship)).all():
        assert f.user_id < f.friend_id, "row must be stored as (min, max)"
        out[(str(f.user_id), str(f.friend_id))] = f.status
    return out


def _key(x, y):
    a, b = _uid(x), _uid(y)
    return (a, b) if uuid.UUID(a) < uuid.UUID(b) else (b, a)


def _snap(db):
    db.expire_all()
    return {
        "log": set(db.scalars(select(ActivityLog.id)).all()),
        "rec": db.scalar(select(func.count()).select_from(ActivityRecipient)),
        "notif": db.scalar(select(func.count()).select_from(Notification)),
    }


def _assert_only_normal_activity(db, before, actions):
    """Only the given group.* rows (from S2-B-6) were added: no friend.added, no extra recipients/outbox rows."""
    db.expire_all()
    new = [r for r in db.scalars(select(ActivityLog)).all() if r.id not in before["log"]]
    assert sorted(r.action for r in new) == sorted(actions)
    new_ids = {r.id for r in new}
    recipient_activity_ids = set(db.scalars(select(ActivityRecipient.activity_id)).all())
    assert recipient_activity_ids <= before["log"] | new_ids
    # every recipient row added belongs to the new group.* rows (checked by count against those rows)
    per_new = db.scalar(select(func.count()).select_from(ActivityRecipient).where(
        ActivityRecipient.activity_id.in_(new_ids))) if new_ids else 0
    assert db.scalar(select(func.count()).select_from(ActivityRecipient)) - before["rec"] == per_new
    assert db.scalar(select(func.count()).select_from(Notification)) == before["notif"]


# ---- vector 52 + 56(iii) -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("a_lt_b", [True, False], ids=["A<B", "A>B"])
def test_vector_52_and_56iii_leave_keeps_friends_ordered_min_max(client, db_session, a_lt_b):
    a, b, c, d = _users_with_order(client, ["Asha", "Ravi", "Meera", "Dev"], a_lt_b)
    assert client.post("/friends", json={"email": d["user"]["email"]}, headers=_h(a)).status_code == 201
    gid = _group(client, a, [b, c])
    assert _rows(db_session) == {_key(a, d): "active"}
    before = _snap(db_session)

    r = _leave(client, a, gid)
    assert r.status_code == 204, r.text

    assert _rows(db_session) == {_key(a, d): "active", _key(a, b): "active", _key(a, c): "active"}
    assert _key(b, c) not in _rows(db_session)  # they still share G1
    assert _friend_ids(client, a) == {_uid(b), _uid(c), _uid(d)}
    assert _friend_ids(client, b) == {_uid(a), _uid(c)}
    assert _friend_ids(client, c) == {_uid(a), _uid(b)}
    _assert_only_normal_activity(db_session, before, ["group.member_removed"])
    # the setup POST /friends (D) legitimately logged friend.added before the snapshot; only NEW rows count
    db_session.expire_all()
    new_rows = [r for r in db_session.scalars(select(ActivityLog)).all() if r.id not in before["log"]]
    assert new_rows and not any(r.action == "friend.added" for r in new_rows)

    # not 404 (explicit row), not 409 (no shared group)
    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 204


def test_56iii_repeated_trigger_never_creates_a_second_row(client, db_session):
    a, b, c = _users_with_order(client, ["Asha", "Ravi", "Meera"], False)
    g1, g2 = _group(client, a, [b], "G1"), _group(client, a, [b, c], "G2")
    assert _leave(client, a, g1).status_code == 204  # A-B still share G2: nothing yet
    assert _rows(db_session) == {}
    assert _leave(client, a, g2).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active", _key(a, c): "active"}
    # A rejoins and leaves again: same two rows
    assert client.post(f"/groups/{g2}/members", json={"user_ids": [_uid(a)]}, headers=_h(b)).status_code in (200, 201)
    assert _leave(client, a, g2).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active", _key(a, c): "active"}


# ---- vector 53 -----------------------------------------------------------------------------------------------------

def test_vector_53_pair_with_another_shared_group_is_not_materialized(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g1, g2 = _group(client, a, [b, c], "G1"), _group(client, a, [b], "G2")
    assert _leave(client, a, g1).status_code == 204
    assert _rows(db_session) == {_key(a, c): "active"}  # A-B share G2, B-C share G1
    assert _friend_ids(client, a) == {_uid(b), _uid(c)}
    assert _leave(client, a, g2).status_code == 204
    assert _rows(db_session) == {_key(a, c): "active", _key(a, b): "active"}
    assert _friend_ids(client, a) == {_uid(b), _uid(c)}


# ---- vector 54 -----------------------------------------------------------------------------------------------------

def test_vector_54_delete_group_materializes_all_pairs(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g1, g2 = _group(client, a, [b, c], "G1"), _group(client, a, [b], "G2")
    before = _snap(db_session)

    assert client.delete(f"/groups/{g1}", headers=_h(a)).status_code == 204
    assert _rows(db_session) == {_key(a, c): "active", _key(b, c): "active"}
    _assert_only_normal_activity(db_session, before, ["group.deleted"])

    r = client.delete(f"/groups/{g1}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_DELETED"
    assert len(_rows(db_session)) == 2

    assert client.delete(f"/groups/{g2}", headers=_h(a)).status_code == 204
    rows = _rows(db_session)
    assert rows == {_key(a, c): "active", _key(b, c): "active", _key(a, b): "active"}
    assert _friend_ids(client, a) == {_uid(b), _uid(c)}
    assert _friend_ids(client, b) == {_uid(a), _uid(c)}
    assert _friend_ids(client, c) == {_uid(a), _uid(b)}


# ---- vector 55 -----------------------------------------------------------------------------------------------------

def test_vector_55_remove_member_materializes_and_refused_removal_writes_nothing(client, db_session, monkeypatch):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g = _group(client, a, [b, c])
    debt = {"on": True}
    bid = uuid.UUID(_uid(b))

    def stub(db, group_id, user_id):
        return [BalanceLine(amount_minor=1, currency="INR")] if debt["on"] and user_id == bid else []

    monkeypatch.setattr("app.services_groups.member_balances", stub)
    before = _snap(db_session)

    r = client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "OUTSTANDING_BALANCE"
    assert _rows(db_session) == {}
    _assert_only_normal_activity(db_session, before, [])
    members = client.get(f"/groups/{g}", headers=_h(a)).json()["members"]
    assert [m["left_at"] for m in members if m["user"]["id"] == _uid(b)] == [None]

    debt["on"] = False  # B settled
    before = _snap(db_session)
    assert client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(a)).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active", _key(b, c): "active"}  # A-C still share G
    assert _friend_ids(client, a) == {_uid(b), _uid(c)}
    assert _friend_ids(client, b) == {_uid(a), _uid(c)}
    assert _friend_ids(client, c) == {_uid(a), _uid(b)}
    _assert_only_normal_activity(db_session, before, ["group.member_removed"])


def test_vector_55_with_real_debt_after_s4_b_3(client, db_session):
    """Vector 55 with a real debt (no stub): B owes 1 INR through a group expense; the guard must read it."""
    from tests.expense_helpers import create_group_expense

    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g = _group(client, a, [b, c])
    body = {"description": "Pen", "total": {"amount_minor": 1, "currency": "INR"}, "expense_date": "2026-11-05",
            "payers": [{"user_id": _uid(a), "paid_amount_minor": 1}],
            "split": {"type": "exact", "entries": [{"user_id": _uid(b), "value": 1}]}}
    create_group_expense(client, a, g, body)  # B net -1
    before = _snap(db_session)

    r = client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "OUTSTANDING_BALANCE", r.text
    assert r.json()["details"]["balances"] == [{"amount_minor": -1, "currency": "INR"}]
    assert _rows(db_session) == {}
    _assert_only_normal_activity(db_session, before, [])

    settle = {**body, "payers": [{"user_id": _uid(b), "paid_amount_minor": 1}],
              "split": {"type": "exact", "entries": [{"user_id": _uid(a), "value": 1}]}}
    create_group_expense(client, b, g, settle)  # B back to 0
    assert client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(a)).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active", _key(b, c): "active"}  # A-C still share G


# ---- refused calls write nothing ----------------------------------------------------------------------------------
# These two pass today (nothing is written at all) and must keep passing after S2-B-8.

def test_refused_calls_write_nothing_403_and_409(client, db_session):
    a, b, z = (_user(client, n) for n in ("Asha", "Ravi", "Zed"))
    g = _group(client, a, [b])
    before = _snap(db_session)
    assert client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(z)).status_code == 403
    assert client.delete(f"/groups/{g}", headers=_h(z)).status_code == 403
    assert client.delete(f"/groups/{g}/members/me", headers=_h(z)).status_code == 403
    assert _rows(db_session) == {}
    _assert_only_normal_activity(db_session, before, [])

    assert client.delete(f"/groups/{g}", headers=_h(a)).status_code == 204  # materializes A-B (S2-B-8)
    n_rows = len(_rows(db_session))
    before = _snap(db_session)
    assert client.delete(f"/groups/{g}/members/{_uid(b)}", headers=_h(a)).status_code == 409  # ALREADY_DELETED
    assert len(_rows(db_session)) == n_rows
    _assert_only_normal_activity(db_session, before, [])


# ---- vector 56 (i), (ii) -------------------------------------------------------------------------------------------

def test_vector_56i_existing_active_row_is_unchanged(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 201
    g = _group(client, a, [b])
    db_session.expire_all()
    row = db_session.scalars(select(Friendship)).one()
    t0, upd0 = row.created_at, row.updated_at
    assert _leave(client, a, g).status_code == 204
    db_session.expire_all()
    rows = db_session.scalars(select(Friendship)).all()
    assert len(rows) == 1
    assert rows[0].status == "active" and rows[0].created_at == t0 and rows[0].removed_at is None
    assert rows[0].updated_at == upd0


def test_vector_56ii_removed_row_is_reactivated_keeping_created_at(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 201
    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 204
    db_session.expire_all()
    row = db_session.scalars(select(Friendship)).one()
    assert row.status == "removed" and row.removed_at is not None
    t0 = row.created_at
    assert _friend_ids(client, a) == set()

    h = _group(client, a, [b], "H")
    assert _rows(db_session) == {_key(a, b): "removed"}  # live group: nothing changes
    assert client.delete(f"/groups/{h}", headers=_h(a)).status_code == 204

    db_session.expire_all()
    rows = db_session.scalars(select(Friendship)).all()
    assert len(rows) == 1
    assert rows[0].status == "active" and rows[0].removed_at is None and rows[0].created_at == t0
    assert _friend_ids(client, a) == {_uid(b)}


# ---- vector 57 -----------------------------------------------------------------------------------------------------

def test_vector_57_explicit_friend_who_still_shares_a_group(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 201
    g = _group(client, a, [b])
    db_session.expire_all()
    t0 = db_session.scalars(select(Friendship)).one().created_at

    r = client.delete(f"/friends/{_uid(b)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "SHARED_GROUPS_EXIST"
    assert r.json()["details"]["group_ids"] == [g]
    assert _rows(db_session) == {_key(a, b): "active"}

    assert _leave(client, b, g).status_code == 204
    db_session.expire_all()
    rows = db_session.scalars(select(Friendship)).all()
    assert len(rows) == 1 and rows[0].status == "active" and rows[0].created_at == t0

    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 204
    db_session.expire_all()
    row = db_session.scalars(select(Friendship)).one()
    assert row.status == "removed" and row.removed_at is not None
    assert _friend_ids(client, a) == set()


# ---- vector 58 -----------------------------------------------------------------------------------------------------

def test_vector_58_restore_does_not_undo(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _group(client, a, [b])
    assert client.delete(f"/groups/{g}", headers=_h(a)).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active"}
    assert _friend_ids(client, a) == {_uid(b)}

    # POST /groups/{id}/restore is V2 (not implemented): restore through the database.
    db_session.execute(update(Group).where(Group.id == uuid.UUID(g)).values(deleted_at=None))
    db_session.commit()

    assert _rows(db_session) == {_key(a, b): "active"}
    assert _friend_ids(client, a) == {_uid(b)}  # once, although explicit and implicit
    r = client.delete(f"/friends/{_uid(b)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "SHARED_GROUPS_EXIST" and r.json()["details"]["group_ids"] == [g]

    assert _leave(client, a, g).status_code == 204
    assert _rows(db_session) == {_key(a, b): "active"}
    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 204


# ---- vector 59 -----------------------------------------------------------------------------------------------------

def test_vector_59_friend_survives_group_delete_and_post_friends_is_200(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _group(client, a, [b])
    assert client.delete(f"/groups/{g}", headers=_h(a)).status_code == 204
    assert _friend_ids(client, a) == {_uid(b)}
    assert client.get(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 200
    r = client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a))
    assert r.status_code == 200, "row already exists after the group ended: 200, not 201"
    assert len(_rows(db_session)) == 1


def test_vector_59_non_group_expense_survives_group_delete(client, db_session):
    """Half of vector 59 that needs no balances: E (A paid 6000, equal A,B) is untouched by deleting G."""
    from tests.expense_helpers import create_expense, equal_body

    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _group(client, a, [b])
    e = create_expense(client, a, {**equal_body(a, [a, b], total=6000, description="Taxi"), "group_id": None})
    assert e["group_id"] is None and e["total"]["amount_minor"] == 6000
    assert client.delete(f"/groups/{g}", headers=_h(a)).status_code == 204

    # E is not deleted: readable by both participants, still non-group, unchanged version
    for who in (a, b):
        r = client.get(f"/expenses/{e['id']}", headers=_h(who))
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["id"] == e["id"] and got["group_id"] is None and got["total"]["amount_minor"] == 6000
        assert got["version"] == e["version"]
        assert got.get("deleted_at") is None

    # A's non-group list for B shows E (also via the friend filter), and B sees it too
    for who, other in ((a, b), (b, a)):
        r = client.get("/expenses", params={"non_group": "true"}, headers=_h(who))
        assert r.status_code == 200, r.text
        assert [i["id"] for i in r.json()["items"]] == [e["id"]]
        r = client.get("/expenses", params={"friend_user_id": _uid(other), "non_group": "true"}, headers=_h(who))
        assert r.status_code == 200, r.text
        assert [i["id"] for i in r.json()["items"]] == [e["id"]]

    # friendship materialized (A-B), listed, and POST /friends is now 200, not 201
    assert _rows(db_session) == {_key(a, b): "active"}
    assert _friend_ids(client, a) == {_uid(b)}
    assert client.get(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 200
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 200


def test_vector_59_non_group_balance_3000_after_s4(client, db_session):
    """After A deletes G, GET /friends/B shows the 3000 INR non-group balance (B owes A) for E."""
    from tests.expense_helpers import create_expense, equal_body

    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _group(client, a, [b])
    create_expense(client, a, {**equal_body(a, [a, b], total=6000, description="Taxi"), "group_id": None})
    assert client.delete(f"/groups/{g}", headers=_h(a)).status_code == 204
    r = client.get(f"/friends/{_uid(b)}", headers=_h(a))
    assert r.status_code == 200, r.text
    f = r.json()
    assert [(x["amount_minor"], x["currency"]) for x in f["balances"]] == [(3000, "INR")]
    assert [(x["scope"], x["group_id"], [(l["amount_minor"], l["currency"]) for l in x["balances"]])
            for x in f["breakdown"]] == [("non_group", None, [(3000, "INR")])]
    fb = client.get(f"/friends/{_uid(a)}", headers=_h(b)).json()
    assert [(x["amount_minor"], x["currency"]) for x in fb["balances"]] == [(-3000, "INR")]


# ---- vector 60 -----------------------------------------------------------------------------------------------------
# Passes today (S2-B-4/S2-B-5 already behave this way); it guards the 201 -> 200 rule after S2-B-8.

def test_vector_60_post_friends_on_implicit_friend(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _group(client, a, [b])
    r = client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a))
    assert r.status_code == 201 and r.json()["is_new_user"] is False
    assert _rows(db_session) == {_key(a, b): "active"}
    r = client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a))
    assert r.status_code == 200
    assert len(_rows(db_session)) == 1
    assert _friend_ids(client, a) == {_uid(b)}
    r = client.delete(f"/friends/{_uid(b)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["details"]["group_ids"] == [g]
