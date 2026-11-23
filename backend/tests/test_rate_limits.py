"""S2-Q-3: login and password-reset rate limits (business_rules 11.2, vector 48; OQ-38). Time is frozen.

Written before S2-B-7. Until it ships nothing returns 429, so each test fails at its first 429 assertion
(the 6th login / 21st IP login / 4th reset returns 401 or 202 instead). That is the missing behaviour.
"""
import pytest

from tests import clock as clockmod
from tests.test_auth import reg


@pytest.fixture()
def clock(monkeypatch):
    return clockmod.install(monkeypatch)


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _reset(client, email):
    return client.post("/auth/password-reset", json={"email": email})


def _assert_limited(r, retry_after):
    assert r.status_code == 429, f"expected 429 RATE_LIMITED, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["code"] == "RATE_LIMITED"
    assert body["details"]["retry_after_seconds"] == retry_after
    assert r.headers["Retry-After"] == str(retry_after)


def _wrong(client, email="a@x.com"):
    r = _login(client, email, "wrong-pass1")
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_vector_48_login_rate_limit_timeline(client, clock):
    clock.set(0)
    reg(client, email="a@x.com")
    reg(client, email="b@x.com", name="Bee")
    for t in (0, 10, 20, 30, 40):
        clock.set(t)
        _wrong(client)

    clock.set(60)
    _assert_limited(_login(client, "a@x.com", "wrong-pass1"), 840)
    _assert_limited(_login(client, "a@x.com", "abcd1234"), 840)  # correct password is limited too
    clock.set(100)
    _assert_limited(_login(client, "a@x.com", "abcd1234"), 800)  # 429s were not counted, window unchanged

    clock.set(60)
    _wrong(client, "b@x.com")  # other email unaffected
    assert _login(client, "b@x.com", "abcd1234").status_code == 200

    clock.set(901)  # t=0 attempt left the window: only 4 failures remain
    assert _login(client, "a@x.com", "abcd1234").status_code == 200


def test_limited_attempts_are_not_counted(client, clock):
    """If the many 429s were counted, the window would never clear at t=901."""
    reg(client, email="a@x.com")
    for t in (0, 10, 20, 30, 40):
        clock.set(t)
        _wrong(client)
    for t in range(41, 61):
        clock.set(t)
        assert _login(client, "a@x.com", "wrong-pass1").status_code == 429
    clock.set(901)
    assert _login(client, "a@x.com", "abcd1234").status_code == 200


def test_login_email_is_case_folded(client, clock):
    reg(client, email="a@x.com")
    for i, e in enumerate(["A@x.com", "a@X.com", "a@x.com", "A@X.COM", "a@x.com"]):
        clock.set(i)
        assert _login(client, e, "wrong-pass1").status_code == 401
    clock.set(10)
    r = _login(client, "A@x.com", "abcd1234")
    assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"


def test_unknown_email_is_counted_like_a_known_one(client, clock):
    for t in range(5):
        clock.set(t)
        assert _login(client, "ghost@x.com", "whatever11").status_code == 401
    clock.set(5)
    _assert_limited(_login(client, "ghost@x.com", "whatever11"), 895)


def test_successful_login_neither_counts_nor_resets(client, clock):
    reg(client, email="a@x.com")
    for t in (0, 1, 2, 3):
        clock.set(t)
        _wrong(client)
    clock.set(4)
    assert _login(client, "a@x.com", "abcd1234").status_code == 200  # does not reset the 4 failures
    clock.set(5)
    _wrong(client)  # 5th failure
    clock.set(6)
    assert _login(client, "a@x.com", "abcd1234").status_code == 429


def test_ip_limit_20_failures_across_different_emails(client, clock):
    reg(client, email="real@x.com")
    for i in range(20):
        clock.set(i)
        assert _login(client, f"user{i}@x.com", "whatever11").status_code == 401  # one per email: email limit not hit
    clock.set(20)
    r = _login(client, "real@x.com", "abcd1234")  # a fresh email, correct password
    assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"
    assert r.json()["details"]["retry_after_seconds"] == 880
    assert r.headers["Retry-After"] == "880"
    clock.set(901)  # oldest failure (t=0) has left the window, 19 remain
    assert _login(client, "real@x.com", "abcd1234").status_code == 200


def test_password_reset_limit_3_per_email_per_hour(client, clock):
    reg(client, email="a@x.com")
    for t in (0, 100, 200):
        clock.set(t)
        assert _reset(client, "a@x.com").status_code == 202
    clock.set(300)
    _assert_limited(_reset(client, "a@x.com"), 3300)
    assert _reset(client, "b@x.com").status_code == 202  # other email unaffected
    clock.set(3601)  # t=0 request left the window
    assert _reset(client, "a@x.com").status_code == 202


def test_password_reset_email_case_folded_and_unknown_email_counted(client, clock):
    for i, e in enumerate(["Ghost@x.com", "ghost@X.com", "GHOST@x.com"]):
        clock.set(i)
        assert _reset(client, e).status_code == 202
    clock.set(3)
    r = _reset(client, "ghost@x.com")
    assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"


def test_login_failures_do_not_consume_reset_budget_and_vice_versa(client, clock):
    reg(client, email="a@x.com")
    for t in range(3):
        clock.set(t)
        assert _reset(client, "a@x.com").status_code == 202
    clock.set(10)
    _wrong(client)  # login still works (401, not 429) after 3 resets


def test_register_and_refresh_are_never_rate_limited(client, clock):
    first = reg(client, email="a@x.com")
    assert first.status_code == 201
    # trip both the email and the IP login limits
    for i in range(20):
        clock.set(i)
        _login(client, "a@x.com" if i < 5 else f"u{i}@x.com", "whatever11")
    clock.set(30)
    assert _login(client, "a@x.com", "abcd1234").status_code == 429

    for i in range(25):
        r = reg(client, email=f"new{i}@x.com")
        assert r.status_code == 201
    for _ in range(25):
        assert reg(client, email="a@x.com").status_code == 409  # duplicate, still not 429
    token = first.json()["refresh_token"]
    for _ in range(25):
        r = client.post("/auth/refresh", json={"refresh_token": token})
        assert r.status_code != 429
        if r.status_code == 200:
            token = r.json()["refresh_token"]
    for _ in range(25):
        assert client.post("/auth/refresh", json={"refresh_token": "garbage"}).status_code == 401
