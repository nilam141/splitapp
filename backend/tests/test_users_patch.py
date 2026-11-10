"""S2-B-3: PATCH /users/me."""
from tests.test_auth import PREF_KEYS, reg


def _h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def test_patch_default_currency_persists(client):
    d = reg(client).json()
    r = client.patch("/users/me", json={"default_currency": "USD"}, headers=_h(d))
    assert r.status_code == 200
    assert r.json()["default_currency"] == "USD"
    assert client.get("/users/me", headers=_h(d)).json()["default_currency"] == "USD"


def test_patch_lowercase_currency_is_normalised(client):
    d = reg(client).json()
    r = client.patch("/users/me", json={"default_currency": "eur"}, headers=_h(d))
    assert r.json()["default_currency"] == "EUR"


def test_patch_unknown_currency_422(client):
    d = reg(client).json()
    r = client.patch("/users/me", json={"default_currency": "ZZZ"}, headers=_h(d))
    assert r.status_code == 422 and r.json()["code"] == "CURRENCY_UNKNOWN"
    assert client.get("/users/me", headers=_h(d)).json()["default_currency"] == "INR"


def test_patch_email_clash_409(client):
    reg(client, email="a@example.com")
    b = reg(client, email="b@example.com").json()
    r = client.patch("/users/me", json={"email": "A@example.com"}, headers=_h(b))
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_TAKEN" and r.json()["details"] == {"field": "email"}


def test_patch_own_email_same_value_ok_and_lowercased(client):
    d = reg(client, email="a@example.com").json()
    r = client.patch("/users/me", json={"email": "A@Example.com"}, headers=_h(d))
    assert r.status_code == 200 and r.json()["email"] == "a@example.com"


def test_patch_phone_clash_409_field_phone(client):
    a = reg(client, email="a@example.com").json()
    b = reg(client, email="b@example.com").json()
    assert client.patch("/users/me", json={"phone_e164": "+919800000001"}, headers=_h(a)).status_code == 200
    r = client.patch("/users/me", json={"phone_e164": "+919800000001"}, headers=_h(b))
    assert r.status_code == 409 and r.json()["details"] == {"field": "phone_e164"}


def test_patch_phone_null_clears_and_bad_phone_422(client):
    d = reg(client).json()
    client.patch("/users/me", json={"phone_e164": "+919800000001"}, headers=_h(d))
    r = client.patch("/users/me", json={"phone_e164": None}, headers=_h(d))
    assert r.status_code == 200 and r.json()["phone_e164"] is None
    assert client.patch("/users/me", json={"phone_e164": "9800000001"}, headers=_h(d)).status_code == 422


def test_patch_one_pref_key_keeps_other_nine(client):
    d = reg(client).json()
    r = client.patch("/users/me", json={"notification_prefs": {"comment_added": False}}, headers=_h(d))
    prefs = r.json()["notification_prefs"]
    assert prefs["comment_added"] is False
    assert set(prefs) == PREF_KEYS
    assert {k for k in PREF_KEYS if prefs[k] is True} == PREF_KEYS - {"comment_added"}
    # second patch keeps the first change
    r = client.patch("/users/me", json={"notification_prefs": {"reminder": False}}, headers=_h(d))
    prefs = r.json()["notification_prefs"]
    assert prefs["comment_added"] is False and prefs["reminder"] is False
    assert sum(1 for v in prefs.values() if v) == 8


def test_patch_validation_errors(client):
    d = reg(client).json()
    for body in ({"name": ""}, {"name": "x" * 101}, {"name": None}, {"time_zone": "Mars/Base"},
                 {"email": "nope"}, {"notification_prefs": {"bogus": True}},
                 {"notification_prefs": {"reminder": None}}):
        r = client.patch("/users/me", json=body, headers=_h(d))
        assert r.status_code == 422, body
        assert r.json()["code"] == "VALIDATION_ERROR"


def test_patch_name_and_time_zone(client):
    d = reg(client).json()
    r = client.patch("/users/me", json={"name": "Asha K", "time_zone": "Europe/London"}, headers=_h(d))
    assert r.status_code == 200
    assert r.json()["name"] == "Asha K" and r.json()["time_zone"] == "Europe/London"


def test_patch_empty_body_is_noop(client):
    d = reg(client).json()
    assert client.patch("/users/me", json={}, headers=_h(d)).status_code == 200


def test_patch_requires_auth(client):
    r = client.patch("/users/me", json={"name": "X"})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"
