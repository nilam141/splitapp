"""S2-B-4: /friends (explicit friendships only until S2-B-5)."""
import uuid

from sqlalchemy import select

from app.models import Friendship, Notification, User

from tests.test_auth import reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def _add(client, d, body, **headers):
    return client.post("/friends", json=body, headers={**_h(d), **headers})


def _two(client):
    a = reg(client, email="a@example.com", name="Asha").json()
    b = reg(client, email="b@example.com", name="Ravi").json()
    return a, b


def test_add_registered_user_201_not_new(client, db_session):
    a, b = _two(client)
    r = _add(client, a, {"email": "b@example.com"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_new_user"] is False
    f = body["friend"]
    assert f["user"] == {"id": b["user"]["id"], "name": "Ravi", "email": "b@example.com", "avatar_url": None,
                         "is_registered": True}
    assert f["balances"] == [] and f["breakdown"] == [] and f["settled_up_since"] is None
    rows = db_session.scalars(select(Friendship)).all()
    assert len(rows) == 1 and rows[0].status == "active" and rows[0].user_id < rows[0].friend_id
    assert db_session.scalars(select(Notification)).all() == []  # registered users get no invite


def test_add_is_symmetric(client):
    a, b = _two(client)
    _add(client, a, {"email": "b@example.com"})
    items = client.get("/friends", headers=_h(b)).json()["items"]
    assert [i["user"]["id"] for i in items] == [a["user"]["id"]]


def test_add_unknown_email_creates_placeholder_and_one_invite(client, db_session):
    a = reg(client).json()
    r = _add(client, a, {"email": "New@Example.com", "name": "New Person"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_new_user"] is True
    assert body["friend"]["user"]["is_registered"] is False
    assert body["friend"]["user"]["email"] == "new@example.com"
    rows = db_session.scalars(select(Notification)).all()
    assert len(rows) == 1
    assert rows[0].type == "invite" and rows[0].channel == "email" and rows[0].status == "pending"
    assert str(rows[0].user_id) == body["friend"]["user"]["id"]
    ph = db_session.get(User, uuid.UUID(body["friend"]["user"]["id"]))
    assert ph.is_registered is False and ph.password_hash is None and str(ph.invited_by) == a["user"]["id"]
    # a placeholder cannot log in
    r = client.post("/auth/login", json={"email": "new@example.com", "password": "whatever1"})
    assert r.status_code == 401


def test_registering_placeholder_email_reuses_the_id(client, db_session):
    a = reg(client).json()
    placeholder = _add(client, a, {"email": "new@example.com", "name": "New Person"}).json()["friend"]["user"]["id"]
    d = reg(client, email="new@example.com", name="Newbie").json()
    assert d["user"]["id"] == placeholder
    assert d["user"]["is_registered"] is True and d["user"]["name"] == "Newbie"
    # the friendship carries over, and the new user logs in normally
    items = client.get("/friends", headers=_h(d)).json()["items"]
    assert [i["user"]["id"] for i in items] == [a["user"]["id"]]
    assert items[0]["user"]["is_registered"] is True
    assert len(db_session.scalars(select(Friendship)).all()) == 1


def test_unknown_email_requires_name(client):
    a = reg(client).json()
    r = _add(client, a, {"email": "new@example.com"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["details"]["fields"][0]["field"] == "name"


def test_add_by_phone_creates_placeholder_without_email_invite(client, db_session):
    a = reg(client).json()
    r = _add(client, a, {"phone_e164": "+919800000002", "name": "Phone Pal"})
    assert r.status_code == 201 and r.json()["is_new_user"] is True
    assert r.json()["friend"]["user"]["email"] is None
    assert db_session.scalars(select(Notification)).all() == []
    assert _add(client, a, {"phone_e164": "+919800000002"}).status_code == 200


def test_add_by_friend_code(client):
    a, b = _two(client)
    r = _add(client, a, {"friend_code": b["user"]["friend_code"].lower()})
    assert r.status_code == 201 and r.json()["friend"]["user"]["id"] == b["user"]["id"]


def test_unknown_friend_code_410(client):
    a = reg(client).json()
    r = _add(client, a, {"friend_code": "NOSUCHCD"})
    assert r.status_code == 410 and r.json()["code"] == "LINK_EXPIRED"


def test_self_422_for_every_identifier(client):
    a = reg(client, email="a@example.com").json()
    for body in ({"email": "A@example.com"}, {"friend_code": a["user"]["friend_code"]}):
        r = _add(client, a, body)
        assert r.status_code == 422 and r.json()["code"] == "CANNOT_FRIEND_SELF"
    client.patch("/users/me", json={"phone_e164": "+919800000009"}, headers=_h(a))
    r = _add(client, a, {"phone_e164": "+919800000009"})
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_FRIEND_SELF"


def test_repeat_add_is_200_with_one_row(client, db_session):
    a, _ = _two(client)
    assert _add(client, a, {"email": "b@example.com"}).status_code == 201
    r = _add(client, a, {"email": "b@example.com"})
    assert r.status_code == 200 and r.json()["is_new_user"] is False
    assert len(db_session.scalars(select(Friendship)).all()) == 1


def test_other_side_adding_back_is_200(client, db_session):
    a, b = _two(client)
    _add(client, a, {"email": "b@example.com"})
    assert _add(client, b, {"email": "a@example.com"}).status_code == 200
    assert len(db_session.scalars(select(Friendship)).all()) == 1


def test_body_must_have_exactly_one_identifier(client):
    a = reg(client).json()
    for body in ({}, {"name": "X"}, {"email": "x@example.com", "phone_e164": "+919800000002"}):
        r = _add(client, a, body)
        assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR", body
    assert _add(client, a, {"phone_e164": "12345"}).status_code == 422


def test_idempotency_key_replays_identical_response(client, db_session):
    a = reg(client).json()
    key = str(uuid.uuid4())
    body = {"email": "new@example.com", "name": "New Person"}
    r1 = _add(client, a, body, **{"Idempotency-Key": key})
    r2 = _add(client, a, body, **{"Idempotency-Key": key})
    assert r1.status_code == r2.status_code == 201
    assert r1.json() == r2.json()
    assert len(db_session.scalars(select(Friendship)).all()) == 1
    assert len(db_session.scalars(select(Notification)).all()) == 1


def test_idempotency_key_is_per_user_and_validated(client):
    a, b = _two(client)
    key = str(uuid.uuid4())
    assert _add(client, a, {"email": "b@example.com"}, **{"Idempotency-Key": key}).status_code == 201
    # same key from another user is independent
    assert _add(client, b, {"email": "a@example.com"}, **{"Idempotency-Key": key}).status_code == 200
    r = _add(client, a, {"email": "b@example.com"}, **{"Idempotency-Key": "not-a-uuid"})
    assert r.status_code == 422


def test_idempotency_key_reused_on_other_endpoint_is_422(client, db_session):
    from app.idempotency import store
    a, _ = _two(client)
    key = uuid.uuid4()
    store(db_session, uuid.UUID(a["user"]["id"]), key, "POST /groups", 201, {"x": 1})
    db_session.commit()
    r = _add(client, a, {"email": "b@example.com"}, **{"Idempotency-Key": str(key)})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_idempotency_key_expires_after_24h(client, db_session):
    from datetime import datetime, timedelta, timezone
    from app.models import IdempotencyKey
    a = reg(client).json()
    key = str(uuid.uuid4())
    body = {"email": "new@example.com", "name": "New Person"}
    assert _add(client, a, body, **{"Idempotency-Key": key}).status_code == 201
    row = db_session.scalars(select(IdempotencyKey)).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    r = _add(client, a, body, **{"Idempotency-Key": key})
    assert r.status_code == 200  # processed afresh: the person is already a friend


def test_failed_request_does_not_store_key(client):
    a = reg(client).json()
    key = str(uuid.uuid4())
    assert _add(client, a, {"email": "new@example.com"}, **{"Idempotency-Key": key}).status_code == 422
    r = _add(client, a, {"email": "new@example.com", "name": "N"}, **{"Idempotency-Key": key})
    assert r.status_code == 201


def _setup_three(client):
    a = reg(client, email="a@example.com", name="Asha").json()
    reg(client, email="b@example.com", name="Bela")
    reg(client, email="c@example.com", name="Chet")
    for e in ("b@example.com", "c@example.com"):
        _add(client, a, {"email": e})
    return a


def test_list_sorted_by_name_and_filters(client):
    a = _setup_three(client)
    items = client.get("/friends", headers=_h(a)).json()["items"]
    assert [i["user"]["name"] for i in items] == ["Bela", "Chet"]
    for f, n in (("all", 2), ("outstanding", 0), ("owes_me", 0), ("i_owe", 0)):
        r = client.get("/friends", params={"filter": f}, headers=_h(a))
        assert r.status_code == 200 and len(r.json()["items"]) == n, f
    assert client.get("/friends", params={"filter": "bogus"}, headers=_h(a)).status_code == 422


def test_get_friend_and_404s(client):
    a = _setup_three(client)
    fid = client.get("/friends", headers=_h(a)).json()["items"][0]["user"]["id"]
    r = client.get(f"/friends/{fid}", headers=_h(a))
    assert r.status_code == 200 and r.json()["user"]["id"] == fid
    assert client.get(f"/friends/{uuid.uuid4()}", headers=_h(a)).status_code == 404
    assert client.get(f"/friends/{a['user']['id']}", headers=_h(a)).status_code == 404
    # a registered user who is not my friend is not visible
    d = reg(client, email="d@example.com").json()
    assert client.get(f"/friends/{d['user']['id']}", headers=_h(a)).status_code == 404
    assert client.get("/friends/not-a-uuid", headers=_h(a)).status_code == 422


def test_delete_friend_then_gone_then_readd(client, db_session):
    a = _setup_three(client)
    fid = client.get("/friends", headers=_h(a)).json()["items"][0]["user"]["id"]
    assert client.delete(f"/friends/{fid}", headers=_h(a)).status_code == 204
    assert [i["user"]["name"] for i in client.get("/friends", headers=_h(a)).json()["items"]] == ["Chet"]
    assert client.get(f"/friends/{fid}", headers=_h(a)).status_code == 404
    r = client.delete(f"/friends/{fid}", headers=_h(a))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    row = db_session.scalars(select(Friendship).where(Friendship.status == "removed")).one()
    assert row.removed_at is not None
    r = _add(client, a, {"email": "b@example.com"})
    assert r.status_code == 201
    db_session.expire_all()
    assert db_session.scalars(select(Friendship)).all().__len__() == 2
    assert all(f.status == "active" for f in db_session.scalars(select(Friendship)).all())


def test_delete_stranger_404(client):
    a = reg(client).json()
    assert client.delete(f"/friends/{uuid.uuid4()}", headers=_h(a)).status_code == 404


def test_friends_require_auth(client):
    for method, path in (("get", "/friends"), ("post", "/friends"), ("get", f"/friends/{uuid.uuid4()}"),
                         ("delete", f"/friends/{uuid.uuid4()}")):
        r = getattr(client, method)(path)
        assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID", (method, path)


def test_friendships_are_private_between_users(client):
    a = _setup_three(client)
    d = reg(client, email="d@example.com").json()
    assert client.get("/friends", headers=_h(d)).json()["items"] == []
    fid = client.get("/friends", headers=_h(a)).json()["items"][0]["user"]["id"]
    assert client.delete(f"/friends/{fid}", headers=_h(d)).status_code == 404
    assert len(client.get("/friends", headers=_h(a)).json()["items"]) == 2
