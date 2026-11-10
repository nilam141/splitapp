"""S2-Q-4: keep friends when a shared group ends (OQ-37a, business_rules 10.1a, vectors 52-60).

Written before S2-B-8. Today leave / remove / delete write no `friendships` row, so every test that expects a new row
fails on the first row-count or status assertion (an AssertionError on `friendships`, not an HTTP or setup error).
Tests that only assert "nothing is written" or that pass for other reasons are noted on the test.

Notes on test seams:
- Restore: `POST /groups/{id}/restore` is V2 and not implemented, so vector 58 restores through the database
  (`deleted_at = NULL`). Restore must not touch friendships, so this is the same observable state.
- Vector 55: the balance guard `member_balances` is stubbed to 0 until S4-B-3. The test seeds B's debt by patching
  that function (`app.services_groups.member_balances`); the patch still works after S4-B-3 only if that name stays.
  A real-balance variant is skipped with a reason referencing S4-B-3.
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


@pytest.mark.skip(reason="needs real group balances: S4-B-3 replaces the stubbed guard; expenses/settlements come in "
                         "S3/S5. The 409-writes-nothing half is covered above through the stub.")
def test_vector_55_with_real_debt_after_s4_b_3():
    raise AssertionError("write once expenses and the real balance guard exist")


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


@pytest.mark.skip(reason="non-group expenses are not implemented (S3-B-*) and the friend balance is [] until S4; the "
                         "list / GET / POST 200 half of vector 59 is covered above. Add: A pays 6000 equal A,B; "
                         "A deletes G; GET /friends/B shows 3000 INR owed to A; the expense is not deleted.")
def test_vector_59_non_group_balance_survives_after_s3_s4():
    raise AssertionError("write once expenses and friend balances exist")


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
