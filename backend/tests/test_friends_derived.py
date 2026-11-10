"""S2-Q-2: derived friend list while groups are live (business_rules 10.1, vectors 43 and 44; OQ-33).

Written against docs/openapi.yaml before S2-B-5. Before it ships, POST /groups does not exist, so each test fails
at the group-creation step (404/405 instead of 201). That is the missing behaviour, not a test defect.
What happens when a group ends is out of scope here (S2-Q-4, vectors 52-60).
"""
from sqlalchemy import func, select

from app.models import Friendship

from tests.test_auth import reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def _user(client, name):
    return reg(client, email=f"{name.lower()}@example.com", name=name).json()


def _uid(d):
    return d["user"]["id"]


def _create_group(client, owner, members, name="G"):
    r = client.post("/groups", json={"name": name, "member_user_ids": [_uid(m) for m in members]}, headers=_h(owner))
    assert r.status_code == 201, f"POST /groups must create the group (got {r.status_code}): {r.text}"
    return r.json()


def _friend_ids(client, d):
    items = client.get("/friends", headers=_h(d)).json()["items"]
    return [i["user"]["id"] for i in items]


def _friendship_count(db_session):
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(Friendship))


def test_vector_43_remove_implicit_only_friend_is_409_and_writes_nothing(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create_group(client, a, [b])
    assert _friendship_count(db_session) == 0

    for _ in range(2):  # repeatable
        r = client.delete(f"/friends/{_uid(b)}", headers=_h(a))
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "SHARED_GROUPS_EXIST"
        assert body["details"]["group_ids"] == [g["id"]]
        assert _friendship_count(db_session) == 0
    # still in the list
    assert _friend_ids(client, a) == [_uid(b)]


def test_vector_43_symmetric_for_the_other_member(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create_group(client, a, [b])
    r = client.delete(f"/friends/{_uid(a)}", headers=_h(b))
    assert r.status_code == 409 and r.json()["code"] == "SHARED_GROUPS_EXIST"
    assert r.json()["details"]["group_ids"] == [g["id"]]
    assert _friendship_count(db_session) == 0


def test_vector_44_derived_list_is_explicit_union_shared_each_once(client, db_session):
    a, b, c, d = (_user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev"))
    assert client.post("/friends", json={"email": "dev@example.com"}, headers=_h(a)).status_code == 201
    assert _friendship_count(db_session) == 1
    _create_group(client, a, [b, c, d], name="G1")

    ids = _friend_ids(client, a)
    assert sorted(ids) == sorted([_uid(b), _uid(c), _uid(d)])
    assert len(ids) == len(set(ids)) == 3  # D is explicit AND shared: listed once

    # exactly the one explicit row (A-D); none for B or C
    db_session.expire_all()
    rows = db_session.scalars(select(Friendship)).all()
    assert len(rows) == 1
    assert {rows[0].user_id, rows[0].friend_id} == {a["user"]["id"], d["user"]["id"]} or \
        {str(rows[0].user_id), str(rows[0].friend_id)} == {_uid(a), _uid(d)}


def test_co_members_see_each_other_without_rows(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    _create_group(client, a, [b, c])
    assert sorted(_friend_ids(client, b)) == sorted([_uid(a), _uid(c)])
    assert sorted(_friend_ids(client, c)) == sorted([_uid(a), _uid(b)])
    assert _friendship_count(db_session) == 0
    # GET /friends/{id} works for an implicit friend
    assert client.get(f"/friends/{_uid(c)}", headers=_h(b)).status_code == 200


def test_user_in_no_shared_group_is_not_listed(client):
    a, b, outsider = (_user(client, n) for n in ("Asha", "Ravi", "Zed"))
    _create_group(client, a, [b])
    assert _uid(outsider) not in _friend_ids(client, a)
    assert _friend_ids(client, outsider) == []
    assert client.get(f"/friends/{_uid(outsider)}", headers=_h(a)).status_code == 404


def test_explicit_friend_who_shares_group_still_cannot_be_removed(client, db_session):
    """business_rules 10.2: the shared-group check comes first, even with an explicit row."""
    a, d = _user(client, "Asha"), _user(client, "Dev")
    client.post("/friends", json={"email": "dev@example.com"}, headers=_h(a))
    g = _create_group(client, a, [d])
    r = client.delete(f"/friends/{_uid(d)}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "SHARED_GROUPS_EXIST"
    assert r.json()["details"]["group_ids"] == [g["id"]]
    assert _friendship_count(db_session) == 1
