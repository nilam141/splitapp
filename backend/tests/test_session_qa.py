"""S1-Q-1 additions for S1-B-5 / S1-B-6 not covered in test_users_me.py (which backend wrote)."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select, update

from app.config import settings
from app.models import RefreshToken, User

from tests.test_auth import PREF_KEYS, reg
from tests.test_users_me import _assert_401, _auth, _token

BOB = {"email": "bob@example.com", "name": "Bob"}


def _refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


def _logout(client, access, refresh):
    return client.post("/auth/logout", json={"refresh_token": refresh}, headers=_auth(access))


# ---- GET /users/me: extra 401 and identity cases ----

def test_me_returns_the_caller_not_another_user(client):
    a = reg(client).json()
    b = reg(client, **BOB).json()
    ra = client.get("/users/me", headers=_auth(a["access_token"])).json()
    rb = client.get("/users/me", headers=_auth(b["access_token"])).json()
    assert ra["email"] == "asha@example.com" and ra["id"] == a["user"]["id"]
    assert rb["email"] == "bob@example.com" and rb["id"] == b["user"]["id"]
    assert ra["id"] != rb["id"] and ra["friend_code"] != rb["friend_code"]


def test_me_after_refresh_uses_rotated_access_token(client):
    d = reg(client).json()
    t = _refresh(client, d["refresh_token"]).json()
    r = client.get("/users/me", headers=_auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["id"] == d["user"]["id"]


def test_me_token_missing_exp_or_sub_rejected(client):
    uid = reg(client).json()["user"]["id"]
    now = int(datetime.now(timezone.utc).timestamp())
    no_exp = jwt.encode({"sub": uid, "type": "access", "iat": now}, settings.jwt_secret, algorithm="HS256")
    no_sub = jwt.encode({"type": "access", "exp": now + 600}, settings.jwt_secret, algorithm="HS256")
    no_type = jwt.encode({"sub": uid, "exp": now + 600}, settings.jwt_secret, algorithm="HS256")
    for tok in (no_exp, no_sub, no_type):
        _assert_401(client.get("/users/me", headers=_auth(tok)))


def test_me_wrong_algorithm_rejected(client):
    uid = reg(client).json()["user"]["id"]
    tok = jwt.encode({"sub": uid, "type": "access", "exp": int(datetime.now(timezone.utc).timestamp()) + 600},
                     settings.jwt_secret, algorithm="HS512")
    _assert_401(client.get("/users/me", headers=_auth(tok)))


def test_me_never_leaks_credentials(client):
    d = reg(client).json()
    text = client.get("/users/me", headers=_auth(d["access_token"])).text
    assert "password" not in text and "abcd1234" not in text


def test_me_rejects_non_get_methods(client):
    """PATCH /users/me is S2-B-3; until then it must not mutate or succeed."""
    d = reg(client).json()
    r = client.patch("/users/me", json={"name": "Hacker"}, headers=_auth(d["access_token"]))
    assert r.status_code in (404, 405)
    assert client.get("/users/me", headers=_auth(d["access_token"])).json()["name"] == "Asha"


# ---- POST /auth/logout ----

def test_logout_revokes_only_the_presented_token_and_it_stays_dead(client):
    d = reg(client).json()
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204
    for _ in range(2):
        r = _refresh(client, d["refresh_token"])
        assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_logout_other_device_stays_valid_and_this_device_is_dead(client):
    d = reg(client).json()
    other = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).json()
    assert other["refresh_token"] != d["refresh_token"]
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204
    # Business rule 11.1 / vector 46: replaying a logout-revoked token is NOT reuse, so order no longer matters.
    assert _refresh(client, d["refresh_token"]).status_code == 401
    assert _refresh(client, other["refresh_token"]).status_code == 200


def test_logout_with_other_users_token_leaves_both_users_valid(client, db_session):
    a = reg(client).json()
    b = reg(client, **BOB).json()
    assert _logout(client, a["access_token"], b["refresh_token"]).status_code == 204
    revoked = db_session.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))).all()
    assert revoked == []  # nothing revoked at all, neither B's nor A's
    assert _refresh(client, b["refresh_token"]).status_code == 200
    assert _refresh(client, a["refresh_token"]).status_code == 200


def test_logout_twice_is_204_and_second_call_revokes_nothing_extra(client, db_session):
    d = reg(client).json()
    other = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).json()
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204
    first = {r.id: r.revoked_at for r in db_session.scalars(select(RefreshToken)).all()}
    db_session.expire_all()
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204
    second = {r.id: r.revoked_at for r in db_session.scalars(select(RefreshToken)).all()}
    assert first == second  # revoked_at of the first logout unchanged, no other row touched
    assert sum(v is not None for v in second.values()) == 1
    assert _refresh(client, other["refresh_token"]).status_code == 200


def test_logout_expired_refresh_token_is_204(client, db_session):
    d = reg(client).json()
    db_session.execute(update(RefreshToken).values(expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db_session.commit()
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204


def test_logout_bad_bearers_are_401_and_revoke_nothing(client, db_session):
    d = reg(client).json()
    uid = d["user"]["id"]
    past = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    bad = {
        "garbage": "not.a.jwt",
        "expired": _token(uid, exp=past),
        "refresh_as_access": d["refresh_token"],
        "type_refresh": _token(uid, type="refresh"),
    }
    for name, tok in bad.items():
        r = _logout(client, tok, d["refresh_token"])
        _assert_401(r)
    assert db_session.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))).all() == []
    assert _refresh(client, d["refresh_token"]).status_code == 200


def test_logout_soft_deleted_user_bearer_is_401(client, db_session):
    d = reg(client).json()
    db_session.execute(update(User).where(User.id == uuid.UUID(d["user"]["id"]))
                       .values(deleted_at=datetime.now(timezone.utc)))
    db_session.commit()
    _assert_401(_logout(client, d["access_token"], d["refresh_token"]))


def test_logout_body_validation(client):
    d = reg(client).json()
    h = _auth(d["access_token"])
    r = client.post("/auth/logout", json={}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    r = client.post("/auth/logout", headers=h)
    assert r.status_code == 422
    assert _refresh(client, d["refresh_token"]).status_code == 200  # untouched


def test_logout_with_access_token_in_body_is_204_and_changes_nothing(client):
    d = reg(client).json()
    assert _logout(client, d["access_token"], d["access_token"]).status_code == 204
    assert _refresh(client, d["refresh_token"]).status_code == 200


def test_logout_uses_rotated_token_after_refresh(client):
    """Mirrors the mobile flow: the old refresh token is dead after rotation, logout must use the new one."""
    d = reg(client).json()
    t = _refresh(client, d["refresh_token"]).json()
    assert _logout(client, t["access_token"], t["refresh_token"]).status_code == 204
    assert _refresh(client, t["refresh_token"]).status_code == 401
