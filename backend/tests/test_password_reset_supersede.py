"""Owner decision: a new reset token invalidates the user's earlier live reset tokens."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import services_auth
from app.models import Notification

from tests.test_auth import reg


@pytest.fixture()
def clock(monkeypatch):
    state = {"now": datetime.now(timezone.utc)}
    monkeypatch.setattr(services_auth, "_utcnow", lambda: state["now"])
    return state


def _request(client, email="asha@example.com"):
    return client.post("/auth/password-reset", json={"email": email})


def _tokens(db_session):
    db_session.expire_all()
    rows = db_session.scalars(select(Notification).where(Notification.type == "password_reset")
                              .order_by(Notification.created_at)).all()
    return rows


def _token_for(db_session, email):
    return [n.payload["token"] for n in _tokens(db_session) if n.payload["to"] == email][-1]


def _confirm(client, token, pw="newpass99"):
    return client.post("/auth/password-reset/confirm", json={"token": token, "new_password": pw})


def test_old_token_invalid_after_second_request_new_works(client, db_session):
    reg(client)
    assert _request(client).status_code == 202
    old = _token_for(db_session, "asha@example.com")
    assert _request(client).status_code == 202
    new = _token_for(db_session, "asha@example.com")
    assert new != old
    r = _confirm(client, old)
    assert r.status_code == 410 and r.json()["code"] == "LINK_EXPIRED"
    assert _confirm(client, new).status_code == 200
    # still single use
    assert _confirm(client, new).status_code == 410


def test_old_token_works_when_no_second_request(client, db_session):
    reg(client)
    _request(client)
    assert _confirm(client, _token_for(db_session, "asha@example.com")).status_code == 200


def test_three_requests_only_last_works(client, db_session):
    reg(client)
    toks = []
    for _ in range(3):
        _request(client)
        toks.append(_token_for(db_session, "asha@example.com"))
    assert [_confirm(client, t).status_code for t in toks[:2]] == [410, 410]
    assert _confirm(client, toks[2]).status_code == 200


def test_other_users_tokens_unaffected(client, db_session):
    reg(client)
    reg(client, email="ben@example.com", name="Ben")
    _request(client, "ben@example.com")
    ben = _token_for(db_session, "ben@example.com")
    _request(client, "asha@example.com")
    _request(client, "asha@example.com")
    assert _confirm(client, ben).status_code == 200


def test_new_token_keeps_60_minute_expiry(client, db_session, clock):
    reg(client)
    _request(client)
    clock["now"] += timedelta(minutes=30)
    _request(client)
    new = _token_for(db_session, "asha@example.com")
    clock["now"] += timedelta(minutes=59)
    r = _confirm(client, new)
    assert r.status_code == 200


def test_new_token_expires_at_60_minutes_from_its_own_issue(client, db_session, clock):
    reg(client)
    _request(client)
    clock["now"] += timedelta(minutes=30)
    _request(client)
    new = _token_for(db_session, "asha@example.com")
    clock["now"] += timedelta(minutes=60)
    assert _confirm(client, new).status_code == 410


def test_unknown_email_unchanged_no_side_effects(client, db_session):
    reg(client)
    _request(client)
    known = _request(client, "asha@example.com")
    unknown = _request(client, "nobody@example.com")
    assert unknown.status_code == known.status_code == 202
    assert unknown.content == known.content
    assert len(_tokens(db_session)) == 2
