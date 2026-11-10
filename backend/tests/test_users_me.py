"""S1-B-5: GET /users/me and the bearer-auth dependency."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import update

from app.config import settings
from app.models import User

from tests.test_auth import PREF_KEYS, reg

USER_ME_KEYS = {
    "id", "email", "name", "phone_e164", "default_currency", "time_zone", "avatar_url", "is_registered",
    "plan", "premium_until", "friend_code", "notification_prefs", "created_at",
}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_401(r):
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    body = r.json()
    assert body["code"] == "TOKEN_INVALID"
    assert isinstance(body["message"], str)


def _token(sub, **over):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(sub), "type": "access", "iat": int(now.timestamp()),
              "exp": int((now + timedelta(minutes=5)).timestamp())}
    claims.update(over)
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_me_returns_full_user_me(client):
    data = reg(client).json()
    r = client.get("/users/me", headers=_auth(data["access_token"]))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == USER_ME_KEYS
    assert body == data["user"]
    assert body["plan"] == "free" and body["premium_until"] is None
    assert set(body["notification_prefs"]) == PREF_KEYS


def test_me_no_header(client):
    _assert_401(client.get("/users/me"))


def test_me_malformed_header(client):
    tok = reg(client).json()["access_token"]
    _assert_401(client.get("/users/me", headers={"Authorization": tok}))
    _assert_401(client.get("/users/me", headers={"Authorization": "Basic abc"}))
    _assert_401(client.get("/users/me", headers={"Authorization": "Bearer "}))


def test_me_garbage_token(client):
    _assert_401(client.get("/users/me", headers=_auth("not.a.jwt")))


def test_me_bad_signature(client):
    uid = reg(client).json()["user"]["id"]
    bad = jwt.encode({"sub": uid, "type": "access", "exp": int(datetime.now(timezone.utc).timestamp()) + 60},
                     "x" * 40, algorithm="HS256")
    _assert_401(client.get("/users/me", headers=_auth(bad)))


def test_me_alg_none_rejected(client):
    uid = reg(client).json()["user"]["id"]
    bad = jwt.encode({"sub": uid, "type": "access", "exp": 4102444800}, None, algorithm="none")
    _assert_401(client.get("/users/me", headers=_auth(bad)))


def test_me_expired_token(client):
    uid = reg(client).json()["user"]["id"]
    past = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    _assert_401(client.get("/users/me", headers=_auth(_token(uid, exp=past))))


def test_me_refresh_token_as_access_token(client):
    data = reg(client).json()
    _assert_401(client.get("/users/me", headers=_auth(data["refresh_token"])))
    # a JWT carrying type=refresh is rejected too
    uid = data["user"]["id"]
    _assert_401(client.get("/users/me", headers=_auth(_token(uid, type="refresh"))))


def test_me_unknown_user_and_bad_sub(client):
    _assert_401(client.get("/users/me", headers=_auth(_token(uuid.uuid4()))))
    _assert_401(client.get("/users/me", headers=_auth(_token("not-a-uuid"))))


def test_me_soft_deleted_user(client, db_session):
    data = reg(client).json()
    db_session.execute(update(User).where(User.id == uuid.UUID(data["user"]["id"]))
                       .values(deleted_at=datetime.now(timezone.utc)))
    db_session.commit()
    _assert_401(client.get("/users/me", headers=_auth(data["access_token"])))


def test_me_placeholder_user(client, db_session):
    data = reg(client).json()
    db_session.execute(update(User).where(User.id == uuid.UUID(data["user"]["id"])).values(is_registered=False))
    db_session.commit()
    _assert_401(client.get("/users/me", headers=_auth(data["access_token"])))


# ---- S1-B-6 POST /auth/logout ----

def _refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


def test_logout_revokes_refresh_token(client):
    d = reg(client).json()
    r = client.post("/auth/logout", json={"refresh_token": d["refresh_token"]}, headers=_auth(d["access_token"]))
    assert r.status_code == 204 and r.content == b""
    r = _refresh(client, d["refresh_token"])
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_logout_twice_and_unknown_token_are_204(client):
    d = reg(client).json()
    h = _auth(d["access_token"])
    for tok in (d["refresh_token"], d["refresh_token"], "rt_unknown"):
        assert client.post("/auth/logout", json={"refresh_token": tok}, headers=h).status_code == 204


def test_logout_other_users_token_revokes_nothing(client):
    a = reg(client).json()
    b = reg(client, email="bob@example.com").json()
    r = client.post("/auth/logout", json={"refresh_token": b["refresh_token"]}, headers=_auth(a["access_token"]))
    assert r.status_code == 204
    assert _refresh(client, b["refresh_token"]).status_code == 200


def test_logout_requires_bearer(client):
    d = reg(client).json()
    r = client.post("/auth/logout", json={"refresh_token": d["refresh_token"]})
    _assert_401(r)
    assert _refresh(client, d["refresh_token"]).status_code == 200


def test_logout_keeps_other_devices(client):
    d = reg(client).json()
    other = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).json()
    client.post("/auth/logout", json={"refresh_token": d["refresh_token"]}, headers=_auth(d["access_token"]))
    assert _refresh(client, other["refresh_token"]).status_code == 200
