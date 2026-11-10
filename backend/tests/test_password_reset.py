"""S2-B-2: /auth/password-reset and /auth/password-reset/confirm."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import services_auth
from app.models import Notification, RefreshToken

from tests.test_auth import reg


@pytest.fixture()
def clock(monkeypatch):
    state = {"now": datetime.now(timezone.utc)}
    monkeypatch.setattr(services_auth, "_utcnow", lambda: state["now"])
    return state


def _request(client, email="asha@example.com"):
    return client.post("/auth/password-reset", json={"email": email})


def _outbox(db_session, type_="password_reset"):
    db_session.expire_all()
    return db_session.scalars(select(Notification).where(Notification.type == type_)).all()


def _token(db_session):
    return _outbox(db_session)[-1].payload["token"]


def _confirm(client, token, pw="newpass99"):
    return client.post("/auth/password-reset/confirm", json={"token": token, "new_password": pw})


def test_request_known_email_writes_one_outbox_row(client, db_session):
    reg(client)
    r = _request(client)
    assert r.status_code == 202
    rows = _outbox(db_session)
    assert len(rows) == 1
    assert rows[0].channel == "email" and rows[0].status == "pending"
    assert rows[0].payload["to"] == "asha@example.com"
    assert rows[0].payload["token"].startswith("pr_")


def test_request_unknown_email_is_202_and_writes_nothing(client, db_session):
    assert _request(client, "nobody@example.com").status_code == 202
    assert _outbox(db_session) == []


def test_request_email_is_case_insensitive(client, db_session):
    reg(client)
    assert _request(client, "ASHA@Example.com").status_code == 202
    assert len(_outbox(db_session)) == 1


def test_request_bad_email_422(client):
    assert _request(client, "not-an-email").status_code == 422


def test_confirm_changes_password_and_returns_session(client, db_session):
    reg(client)
    _request(client)
    r = _confirm(client, _token(db_session))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in", "user"}
    assert client.post("/auth/login", json={"email": "asha@example.com", "password": "newpass99"}).status_code == 200
    old = client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"})
    assert old.status_code == 401 and old.json()["code"] == "INVALID_CREDENTIALS"
    assert client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200


def test_confirm_revokes_live_tokens_with_reason_password_reset(client, db_session):
    old = reg(client).json()
    _request(client)
    new = _confirm(client, _token(db_session)).json()
    r = client.post("/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"
    db_session.expire_all()
    rows = db_session.scalars(select(RefreshToken)).all()
    assert [t.revoked_reason for t in rows if t.revoked_at].count("password_reset") == 1
    assert sum(1 for t in rows if t.revoked_at is None) == 1  # only the fresh session's token is live
    # a password_reset-revoked token replayed revokes nothing else (S1-B-7): the new session keeps working
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200


def test_token_is_single_use(client, db_session):
    reg(client)
    _request(client)
    token = _token(db_session)
    assert _confirm(client, token).status_code == 200
    r = _confirm(client, token, "another-pass1")
    assert r.status_code == 410 and r.json()["code"] == "LINK_EXPIRED"
    # password was not changed by the second attempt
    assert client.post("/auth/login", json={"email": "asha@example.com", "password": "newpass99"}).status_code == 200


def test_token_expires_at_60_minutes(client, db_session, clock):
    reg(client)
    _request(client)
    token = _token(db_session)
    clock["now"] += timedelta(minutes=59, seconds=59)
    ok_probe = _confirm(client, "pr_wrong")  # unknown token is also 410, state unchanged
    assert ok_probe.status_code == 410
    clock["now"] += timedelta(seconds=1)  # exactly 60 minutes
    r = _confirm(client, token)
    assert r.status_code == 410 and r.json()["code"] == "LINK_EXPIRED"
    assert client.post("/auth/login", json={"email": "asha@example.com", "password": "abcd1234"}).status_code == 200


def test_token_valid_just_before_60_minutes(client, db_session, clock):
    reg(client)
    _request(client)
    token = _token(db_session)
    clock["now"] += timedelta(minutes=59, seconds=59)
    assert _confirm(client, token).status_code == 200


def test_confirm_short_password_422(client, db_session):
    reg(client)
    _request(client)
    token = _token(db_session)
    r = _confirm(client, token, "short")
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert _confirm(client, token).status_code == 200  # token not consumed by the failed attempt


def test_placeholder_gets_no_reset_email(client, db_session):
    d = reg(client).json()
    h = {"Authorization": f"Bearer {d['access_token']}"}
    client.post("/friends", json={"email": "ghost@example.com", "name": "Ghost"}, headers=h)
    assert _request(client, "ghost@example.com").status_code == 202
    assert _outbox(db_session) == []
