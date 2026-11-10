"""S1-Q-1: extra auth tests against docs/openapi.yaml (AuthResponse, TokenPair, UserMe, Error)."""
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select, update

from app.config import settings
from app.models import RefreshToken, User

from tests.test_auth import PREF_KEYS, reg


def _is_iso_dt(s):
    datetime.fromisoformat(s.replace("Z", "+00:00"))
    return True


def _assert_user_me(u):
    uuid.UUID(u["id"])
    assert isinstance(u["email"], str) and isinstance(u["name"], str)
    assert u["phone_e164"] is None and u["avatar_url"] is None
    assert re.fullmatch(r"[A-Z]{3}", u["default_currency"])
    assert isinstance(u["time_zone"], str)
    assert u["is_registered"] is True
    assert u["plan"] in ("free", "premium")
    assert _is_iso_dt(u["created_at"])
    assert set(u["notification_prefs"]) == PREF_KEYS


def test_register_and_login_user_objects_are_identical_and_typed(client):
    a = reg(client).json()
    b = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).json()
    _assert_user_me(a["user"])
    assert a["user"] == b["user"]
    assert isinstance(a["expires_in"], int) and b["expires_in"] == 900
    assert a["refresh_token"] != b["refresh_token"]


def test_friend_code_format(client):
    code = reg(client).json()["user"]["friend_code"]
    assert re.fullmatch(r"[A-Z2-9]{8}", code) and not set(code) & set("OIL01")


def test_access_token_claims_and_lifetime(client):
    b = reg(client).json()
    claims = jwt.decode(b["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == b["user"]["id"]
    assert claims["exp"] - claims["iat"] == 900 == settings.access_token_seconds
    # token signed with another key is not valid
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(b["access_token"], "other-secret-other-secret-other-secret", algorithms=["HS256"])


def test_refresh_response_is_token_pair_with_fresh_access_token(client):
    first = reg(client).json()
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    b = r.json()
    assert set(b) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert b["token_type"] == "bearer" and b["expires_in"] == 900
    assert b["refresh_token"].startswith("rt_")
    claims = jwt.decode(b["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == first["user"]["id"]
    assert b["access_token"] != first["access_token"]


def test_refresh_rotation_marks_old_row_revoked_and_adds_new(client, db_session):
    first = reg(client).json()
    client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    rows = db_session.scalars(select(RefreshToken)).all()
    assert len(rows) == 2
    assert sum(r.revoked_at is not None for r in rows) == 1
    # raw tokens are never stored
    assert all(first["refresh_token"].encode() not in bytes(r.token_hash) for r in rows)


def test_reuse_revokes_all_live_tokens_including_other_sessions(client, db_session):
    s1 = reg(client).json()
    s2 = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).json()
    rotated = client.post("/auth/refresh", json={"refresh_token": s1["refresh_token"]}).json()
    # replay s1's old token: whole family for the user dies
    assert client.post("/auth/refresh", json={"refresh_token": s1["refresh_token"]}).status_code == 401
    for tok in (s2["refresh_token"], rotated["refresh_token"]):
        r = client.post("/auth/refresh", json={"refresh_token": tok})
        assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"
    assert all(r.revoked_at is not None for r in db_session.scalars(select(RefreshToken)))


def test_reuse_does_not_revoke_other_users(client):
    a = reg(client).json()
    b = reg(client, email="bob@example.com", name="Bob").json()
    client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})  # replay
    assert client.post("/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 200


def test_expired_refresh_token_is_rejected_and_not_rotated(client, db_session):
    tok = reg(client).json()["refresh_token"]
    db_session.execute(update(RefreshToken).values(expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db_session.commit()
    assert client.post("/auth/refresh", json={"refresh_token": tok}).status_code == 401
    assert len(db_session.scalars(select(RefreshToken)).all()) == 1


def test_refresh_for_soft_deleted_user_401(client, db_session):
    tok = reg(client).json()["refresh_token"]
    db_session.execute(update(User).values(deleted_at=datetime.now(timezone.utc)))
    db_session.commit()
    r = client.post("/auth/refresh", json={"refresh_token": tok})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_login_soft_deleted_user_401(client, db_session):
    reg(client)
    db_session.execute(update(User).values(deleted_at=datetime.now(timezone.utc)))
    db_session.commit()
    r = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_login_placeholder_user_cannot_log_in(client, db_session):
    db_session.add(User(email="ghost@example.com", name="Ghost", is_registered=False, default_currency="INR",
                        notification_prefs={k: True for k in PREF_KEYS}, friend_code="GHOSTCDE"))
    db_session.commit()
    r = client.post("/auth/login", json={"email": "ghost@example.com", "password": "abcd1234"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_register_claims_placeholder_and_keeps_id(client, db_session):
    ph = User(email="ravi@example.com", name="ravi", is_registered=False, default_currency="INR",
              notification_prefs={k: True for k in PREF_KEYS}, friend_code="PLACEHLD")
    db_session.add(ph)
    db_session.commit()
    r = reg(client, email="Ravi@Example.com", name="Ravi")
    assert r.status_code == 201
    assert r.json()["user"]["id"] == str(ph.id)
    assert r.json()["user"]["name"] == "Ravi"
    assert r.json()["user"]["friend_code"] == "PLACEHLD"
    assert reg(client, email="ravi@example.com").status_code == 409


@pytest.mark.parametrize("pw,status", [("a" * 7, 422), ("a" * 8, 201), ("a" * 128, 201), ("a" * 129, 422)])
def test_password_length_bounds(client, pw, status):
    assert reg(client, password=pw).status_code == status


@pytest.mark.parametrize("name,status", [("", 422), ("N", 201), ("N" * 100, 201), ("N" * 101, 422)])
def test_name_length_bounds(client, name, status):
    assert reg(client, name=name).status_code == status


def test_missing_required_fields_report_each_field(client):
    r = client.post("/auth/register", json={})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert {f["field"] for f in r.json()["details"]["fields"]} == {"email", "password", "name"}
    for f in r.json()["details"]["fields"]:
        assert set(f) == {"field", "message"}


def test_login_and_refresh_validation_errors(client):
    r = client.post("/auth/login", json={"email": "nope"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    r = client.post("/auth/refresh", json={})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_currency_unknown_details_and_case_insensitive_known(client):
    r = reg(client, default_currency="ZZZ")
    assert r.status_code == 422 and r.json()["code"] == "CURRENCY_UNKNOWN"
    assert set(r.json()) <= {"code", "message", "details"}
    # nothing was created
    assert reg(client, email="asha@example.com", default_currency="usd").json()["user"]["default_currency"] == "USD"


def test_failed_register_creates_no_user_or_token(client, db_session):
    reg(client, default_currency="ZZZ")
    assert db_session.scalars(select(User)).all() == []
    assert db_session.scalars(select(RefreshToken)).all() == []


def test_error_bodies_follow_error_schema(client):
    reg(client)
    bodies = [
        reg(client),
        client.post("/auth/login", json={"email": "asha@example.com", "password": "bad-password"}),
        client.post("/auth/refresh", json={"refresh_token": "x"}),
        reg(client, default_currency="ZZZ"),
    ]
    for r in bodies:
        b = r.json()
        assert isinstance(b["code"], str) and isinstance(b["message"], str)
        assert set(b) <= {"code", "message", "details"}
    assert bodies[2].headers.get("www-authenticate") == "Bearer"


def test_users_me_returns_the_registered_user(client):
    """Replaces the Slice 1 known-gap test: GET /users/me is implemented (S1-B-5) and returns the UserMe."""
    d = reg(client).json()
    r = client.get("/users/me", headers={"Authorization": f"Bearer {d['access_token']}"})
    assert r.status_code == 200
    body = r.json()
    assert body == d["user"]
    assert body["plan"] == "free" and len(body["friend_code"]) >= 6
    assert set(body["notification_prefs"]) == PREF_KEYS and all(v is True for v in body["notification_prefs"].values())
