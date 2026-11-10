"""S2-B-5: group endpoints."""
import uuid

from sqlalchemy import func, select

from app.models import Friendship, Notification

from tests.test_auth import reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def _user(client, name):
    return reg(client, email=f"{name.lower()}@example.com", name=name).json()


def _uid(d):
    return d["user"]["id"]


def _create(client, owner, **body):
    body.setdefault("name", "G")
    return client.post("/groups", json=body, headers=_h(owner))


def test_create_with_two_ids_and_one_new_member(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    r = _create(client, a, member_user_ids=[_uid(b), _uid(c)], new_members=[{"name": "Kiran", "email": "k@example.com"}])
    assert r.status_code == 201, r.text
    g = r.json()
    assert len(g["members"]) == 4
    assert [m["user"]["id"] for m in g["members"][:3]] == [_uid(a), _uid(b), _uid(c)]
    assert g["members"][3]["user"]["is_registered"] is False
    assert g["version"] == 1 and g["simplify_debts"] is True and g["group_type"] == "other"
    assert g["default_currency"] == "INR" and g["created_by"] == _uid(a) and g["deleted_at"] is None
    assert g["my_balances"] == [] and all(m["balances"] == [] for m in g["members"])
    from app.models import GroupMember
    db_session.expire_all()
    rows = db_session.scalars(select(GroupMember).where(GroupMember.group_id == uuid.UUID(g["id"]))
                              .order_by(GroupMember.sort_index)).all()
    assert [m.sort_index for m in rows] == [0, 1, 2, 3] and str(rows[0].user_id) == _uid(a)
    assert db_session.scalar(select(func.count()).select_from(Friendship)) == 0
    # placeholder invite queued
    assert db_session.scalar(select(func.count()).select_from(Notification).where(Notification.type == "invite")) == 1


def test_validation(client):
    a = _user(client, "Asha")
    assert _create(client, a, name="x" * 101).status_code == 422
    assert _create(client, a, name="").status_code == 422
    assert _create(client, a, name="x" * 100).status_code == 201
    r = _create(client, a, group_type="trip", trip_start_date="2026-12-20", trip_end_date="2026-12-19")
    assert r.status_code == 422 and r.json()["code"] == "INVALID_DATE_RANGE"
    r = _create(client, a, default_currency="ZZZ")
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    r = _create(client, a, member_user_ids=[str(uuid.uuid4())])
    assert r.status_code == 422
    assert client.post("/groups", json={"name": "G"}).status_code == 401


def test_group_too_large(client):
    a = _user(client, "Asha")
    r = _create(client, a, new_members=[{"name": f"P{i}"} for i in range(200)])  # 200 + creator = 201
    assert r.status_code == 422 and r.json()["code"] == "GROUP_TOO_LARGE"
    r = _create(client, a, new_members=[{"name": f"P{i}"} for i in range(199)])  # exactly 200
    assert r.status_code == 201 and len(r.json()["members"]) == 200
    gid = r.json()["id"]
    r = client.post(f"/groups/{gid}/members", json={"new_members": [{"name": "one more"}]}, headers=_h(a))
    assert r.status_code == 422 and r.json()["code"] == "GROUP_TOO_LARGE"


def test_get_authorization(client):
    a, b, z = (_user(client, n) for n in ("Asha", "Ravi", "Zed"))
    g = _create(client, a, member_user_ids=[_uid(b)]).json()
    assert client.get(f"/groups/{g['id']}", headers=_h(b)).status_code == 200
    r = client.get(f"/groups/{g['id']}", headers=_h(z))
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    assert client.get(f"/groups/{uuid.uuid4()}", headers=_h(a)).status_code == 404
    assert client.patch(f"/groups/{g['id']}", json={"version": 1, "name": "n"}, headers=_h(z)).status_code == 403
    assert client.delete(f"/groups/{g['id']}", headers=_h(z)).status_code == 403
    assert client.post(f"/groups/{g['id']}/members", json={}, headers=_h(z)).status_code == 403
    assert client.delete(f"/groups/{g['id']}/members/{_uid(b)}", headers=_h(z)).status_code == 403


def test_patch_version_and_fields(client):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create(client, a, member_user_ids=[_uid(b)]).json()
    r = client.patch(f"/groups/{g['id']}", json={"version": 1, "name": "Flat", "simplify_debts": False,
                                                 "whiteboard": "hi"}, headers=_h(b))  # any member may edit
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Flat" and body["simplify_debts"] is False and body["version"] == 2
    assert body["whiteboard"] == "hi"
    r = client.patch(f"/groups/{g['id']}", json={"version": 1, "name": "Stale"}, headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert r.json()["details"]["current_version"] == 2
    # no-op keeps the version; date range checked against stored values
    assert client.patch(f"/groups/{g['id']}", json={"version": 2, "name": "Flat"}, headers=_h(a)).json()["version"] == 2
    client.patch(f"/groups/{g['id']}", json={"version": 2, "trip_start_date": "2026-12-20"}, headers=_h(a))
    r = client.patch(f"/groups/{g['id']}", json={"version": 3, "trip_end_date": "2026-12-01"}, headers=_h(a))
    assert r.status_code == 422 and r.json()["code"] == "INVALID_DATE_RANGE"
    assert client.patch(f"/groups/{g['id']}", json={"name": "no version"}, headers=_h(a)).status_code == 422
    assert client.patch(f"/groups/{g['id']}", json={"version": 3, "name": None}, headers=_h(a)).status_code == 422


def test_delete_hides_group_and_twice_is_409(client):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create(client, a, member_user_ids=[_uid(b)]).json()
    for u in (a, b):
        assert [i["id"] for i in client.get("/groups", headers=_h(u)).json()["items"]] == [g["id"]]
    assert client.delete(f"/groups/{g['id']}", headers=_h(b)).status_code == 204
    for u in (a, b):
        assert client.get("/groups", headers=_h(u)).json()["items"] == []
    r = client.delete(f"/groups/{g['id']}", headers=_h(a))
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_DELETED"
    got = client.get(f"/groups/{g['id']}", headers=_h(a)).json()
    assert got["deleted_at"] is not None
    assert client.patch(f"/groups/{g['id']}", json={"version": 2, "name": "x"}, headers=_h(a)).status_code == 409


def test_list_shape(client):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create(client, a, member_user_ids=[_uid(b)], group_type="home").json()
    body = client.get("/groups", headers=_h(a)).json()
    assert body["non_group_balances"] == []
    item = body["items"][0]
    assert item["id"] == g["id"] and item["member_count"] == 2 and item["my_balances"] == []
    assert item["group_type"] == "home" and "updated_at" in item


def test_add_and_remove_members(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g = _create(client, a, member_user_ids=[_uid(b)]).json()
    r = client.post(f"/groups/{g['id']}/members", json={"user_ids": [_uid(c), _uid(b)],
                                                        "new_members": [{"name": "Kiran"}]}, headers=_h(b))
    assert r.status_code == 200
    ids = [m["user"]["id"] for m in r.json()["members"]]
    assert ids[:3] == [_uid(a), _uid(b), _uid(c)] and len(ids) == 4  # b already a member: ignored
    assert client.get("/groups", headers=_h(c)).json()["items"][0]["member_count"] == 4

    assert client.delete(f"/groups/{g['id']}/members/{_uid(c)}", headers=_h(a)).status_code == 204
    assert client.get(f"/groups/{g['id']}", headers=_h(c)).status_code == 403
    assert client.get("/groups", headers=_h(c)).json()["items"] == []
    r = client.delete(f"/groups/{g['id']}/members/{_uid(c)}", headers=_h(a))
    assert r.status_code == 404
    assert client.delete(f"/groups/{g['id']}/members/me", headers=_h(b)).status_code == 204  # leave
    assert client.delete(f"/groups/{g['id']}/members/not-a-uuid", headers=_h(a)).status_code == 422
    members = client.get(f"/groups/{g['id']}", headers=_h(a)).json()["members"]
    assert {m["user"]["id"]: m["left_at"] is not None for m in members}[_uid(c)] is True
    # re-adding a departed member reactivates them at the end
    r = client.post(f"/groups/{g['id']}/members", json={"user_ids": [_uid(c)]}, headers=_h(a))
    assert r.status_code == 200
    assert client.get(f"/groups/{g['id']}", headers=_h(c)).status_code == 200


def test_same_idempotency_key_creates_one_group(client):
    a = _user(client, "Asha")
    key = str(uuid.uuid4())
    h = {**_h(a), "Idempotency-Key": key}
    r1 = client.post("/groups", json={"name": "G"}, headers=h)
    r2 = client.post("/groups", json={"name": "G"}, headers=h)
    assert r1.status_code == r2.status_code == 201 and r1.json() == r2.json()
    assert len(client.get("/groups", headers=_h(a)).json()["items"]) == 1
    assert client.post("/groups", json={"name": "G"}, headers={**_h(a), "Idempotency-Key": "bad"}).status_code == 422


def test_group_co_members_appear_in_friends_with_no_rows(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    _create(client, a, member_user_ids=[_uid(b), _uid(c)])
    for me, others in ((a, (b, c)), (b, (a, c)), (c, (a, b))):
        ids = [i["user"]["id"] for i in client.get("/friends", headers=_h(me)).json()["items"]]
        assert sorted(ids) == sorted(_uid(o) for o in others)
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Friendship)) == 0


def test_ended_shared_group_stops_deriving_but_friendship_is_kept(client):
    """Updated for S2-B-8 (OQ-37a): the pair is derived while a group is shared, then kept as an explicit row."""
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    g = _create(client, a, member_user_ids=[_uid(b)]).json()
    client.delete(f"/groups/{g['id']}/members/me", headers=_h(b))
    assert [i["user"]["id"] for i in client.get("/friends", headers=_h(a)).json()["items"]] == [_uid(b)]
    g2 = _create(client, a, member_user_ids=[_uid(b)]).json()
    assert len(client.get("/friends", headers=_h(a)).json()["items"]) == 1  # listed once
    client.delete(f"/groups/{g2['id']}", headers=_h(a))
    assert len(client.get("/friends", headers=_h(a)).json()["items"]) == 1
