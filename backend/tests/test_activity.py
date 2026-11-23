"""S2-B-6: activity_log / activity_recipients writes for group and friend events."""
import uuid

from sqlalchemy import func, select

from app.models import ActivityLog, ActivityRecipient

from tests.test_auth import reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def _user(client, name):
    return reg(client, email=f"{name.lower()}@example.com", name=name).json()


def _uid(d):
    return d["user"]["id"]


def _rows(db, action=None):
    db.expire_all()
    q = select(ActivityLog).order_by(ActivityLog.created_at)
    if action:
        q = q.where(ActivityLog.action == action)
    return db.scalars(q).all()


def _recipients(db, act):
    return sorted(str(r) for r in db.scalars(select(ActivityRecipient.user_id).where(
        ActivityRecipient.activity_id == act.id)))


def test_group_with_three_members_writes_one_created_and_three_recipients(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g = client.post("/groups", json={"name": "Flat", "member_user_ids": [_uid(b), _uid(c)]}, headers=_h(a)).json()
    rows = _rows(db_session)
    assert [r.action for r in rows] == ["group.created"]
    act = rows[0]
    assert str(act.actor_id) == _uid(a) and act.entity_type == "group" and str(act.entity_id) == g["id"]
    assert str(act.group_id) == g["id"] and act.payload["name"] == "Flat"
    assert _recipients(db_session, act) == sorted([_uid(a), _uid(b), _uid(c)])
    assert db_session.scalar(select(func.count()).select_from(ActivityRecipient)) == 3


def test_placeholders_are_not_recipients(client, db_session):
    a = _user(client, "Asha")
    client.post("/groups", json={"name": "G", "new_members": [{"name": "Kiran", "email": "k@example.com"}]},
                headers=_h(a))
    assert _recipients(db_session, _rows(db_session)[0]) == [_uid(a)]


def test_idempotent_replay_writes_one_activity(client, db_session):
    a = _user(client, "Asha")
    h = {**_h(a), "Idempotency-Key": str(uuid.uuid4())}
    client.post("/groups", json={"name": "G"}, headers=h)
    client.post("/groups", json={"name": "G"}, headers=h)
    assert len(_rows(db_session, "group.created")) == 1


def test_group_update_delete_and_member_events(client, db_session):
    a, b, c = (_user(client, n) for n in ("Asha", "Ravi", "Meera"))
    g = client.post("/groups", json={"name": "G", "member_user_ids": [_uid(b)]}, headers=_h(a)).json()
    client.patch(f"/groups/{g['id']}", json={"version": 1, "name": "H"}, headers=_h(b))
    upd = _rows(db_session, "group.updated")
    assert len(upd) == 1 and str(upd[0].actor_id) == _uid(b)
    assert upd[0].payload["changes"] == {"name": {"from": "G", "to": "H"}}
    assert _recipients(db_session, upd[0]) == sorted([_uid(a), _uid(b)])
    # a no-op PATCH and a refused one write nothing
    client.patch(f"/groups/{g['id']}", json={"version": 2, "name": "H"}, headers=_h(b))
    client.patch(f"/groups/{g['id']}", json={"version": 1, "name": "Z"}, headers=_h(b))
    assert len(_rows(db_session, "group.updated")) == 1

    client.post(f"/groups/{g['id']}/members", json={"user_ids": [_uid(c)]}, headers=_h(a))
    added = _rows(db_session, "group.member_added")
    assert len(added) == 1 and added[0].payload["user_id"] == _uid(c)
    assert _recipients(db_session, added[0]) == sorted([_uid(a), _uid(b), _uid(c)])
    client.post(f"/groups/{g['id']}/members", json={"user_ids": [_uid(c)]}, headers=_h(a))  # already a member
    assert len(_rows(db_session, "group.member_added")) == 1

    client.delete(f"/groups/{g['id']}/members/{_uid(c)}", headers=_h(a))
    rem = _rows(db_session, "group.member_removed")
    assert len(rem) == 1 and _recipients(db_session, rem[0]) == sorted([_uid(a), _uid(b), _uid(c)])

    client.delete(f"/groups/{g['id']}", headers=_h(a))
    dele = _rows(db_session, "group.deleted")
    assert len(dele) == 1 and _recipients(db_session, dele[0]) == sorted([_uid(a), _uid(b)])
    client.delete(f"/groups/{g['id']}", headers=_h(a))  # 409 writes nothing
    assert len(_rows(db_session, "group.deleted")) == 1


def test_friend_added_and_removed_events(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 201
    added = _rows(db_session, "friend.added")
    assert len(added) == 1 and added[0].entity_type == "friendship" and added[0].group_id is None
    assert str(added[0].actor_id) == _uid(a) and str(added[0].entity_id) == _uid(b)
    assert _recipients(db_session, added[0]) == sorted([_uid(a), _uid(b)])
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=_h(a)).status_code == 200
    assert len(_rows(db_session, "friend.added")) == 1  # 200 (already friends) writes nothing

    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 204
    rem = _rows(db_session, "friend.removed")
    assert len(rem) == 1 and _recipients(db_session, rem[0]) == sorted([_uid(a), _uid(b)])
    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 404
    assert len(_rows(db_session, "friend.removed")) == 1


def test_refused_friend_removal_writes_no_activity(client, db_session):
    a, b = _user(client, "Asha"), _user(client, "Ravi")
    client.post("/groups", json={"name": "G", "member_user_ids": [_uid(b)]}, headers=_h(a))
    before = len(_rows(db_session))
    assert client.delete(f"/friends/{_uid(b)}", headers=_h(a)).status_code == 409
    assert len(_rows(db_session)) == before
