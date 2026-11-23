"""S2-B-7: the limits come from settings; the window slides; limits are per key."""
import pytest

from app.config import settings
from tests import clock as clockmod
from tests.test_auth import reg


@pytest.fixture()
def clock(monkeypatch):
    return clockmod.install(monkeypatch)


def _login(client, email, pw):
    return client.post("/auth/login", json={"email": email, "password": pw})


def test_limits_follow_settings(client, clock, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures_per_email", 2)
    monkeypatch.setattr(settings, "login_window_seconds", 60)
    reg(client, email="a@x.com")
    for t in (0, 1):
        clock.set(t)
        assert _login(client, "a@x.com", "wrong-pass1").status_code == 401
    clock.set(2)
    r = _login(client, "a@x.com", "abcd1234")
    assert r.status_code == 429 and r.json()["details"]["retry_after_seconds"] == 58
    clock.set(61)  # the t=0 failure left the 60 s window
    assert _login(client, "a@x.com", "abcd1234").status_code == 200


def test_reset_limit_follows_settings(client, clock, monkeypatch):
    monkeypatch.setattr(settings, "reset_max_per_email", 1)
    clock.set(0)
    assert client.post("/auth/password-reset", json={"email": "a@x.com"}).status_code == 202
    clock.set(1)
    r = client.post("/auth/password-reset", json={"email": "a@x.com"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "3599"
