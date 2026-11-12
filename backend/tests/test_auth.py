import jwt

from app.config import settings

PREF_KEYS = {
    "expense_added", "expense_updated", "comment_added", "added_to_group", "removed_from_group",
    "group_updated", "friend_added", "friend_removed", "payment_recorded", "reminder",
}
USER_KEYS = {
    "id", "email", "name", "phone_e164", "default_currency", "time_zone", "avatar_url", "is_registered",
    "plan", "premium_until", "friend_code", "notification_prefs", "created_at",
}


def reg(client, **over):
    body = {"email": "asha@example.com", "password": "abcd1234", "name": "Asha"}
    body.update(over)
    return client.post("/auth/register", json=body)


def test_register_success_matches_auth_response(client):
    r = reg(client)
    assert r.status_code == 201
    b = r.json()
    assert set(b) == {"access_token", "refresh_token", "token_type", "expires_in", "user"}
    assert b["token_type"] == "bearer"
    assert b["expires_in"] == 900
    u = b["user"]
    assert set(u) == USER_KEYS
    assert u["plan"] == "free"
    assert u["premium_until"] is None
    assert u["is_registered"] is True
    assert u["default_currency"] == "INR"
    assert u["time_zone"] == "Asia/Kolkata"
    assert len(u["friend_code"]) >= 6
    assert set(u["notification_prefs"]) == PREF_KEYS
    assert all(v is True for v in u["notification_prefs"].values())
    assert "password" not in u and "password_hash" not in u
    claims = jwt.decode(b["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == u["id"]
    assert claims["exp"] - claims["iat"] == 900


def test_register_custom_currency_and_tz(client):
    r = reg(client, default_currency="jpy", time_zone="Asia/Tokyo")
    assert r.status_code == 201
    assert r.json()["user"]["default_currency"] == "JPY"
    assert r.json()["user"]["time_zone"] == "Asia/Tokyo"


def test_friend_codes_differ(client):
    a = reg(client).json()["user"]["friend_code"]
    b = reg(client, email="b@example.com").json()["user"]["friend_code"]
    assert a != b


def test_duplicate_email_409(client):
    assert reg(client).status_code == 201
    r = reg(client, email="ASHA@example.com")
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_TAKEN"
    assert r.json()["details"] == {"field": "email"}


def test_unknown_currency_422(client):
    r = reg(client, default_currency="XXX")
    assert r.status_code == 422
    assert r.json()["code"] == "CURRENCY_UNKNOWN"


def test_validation_errors_use_error_schema(client):
    r = reg(client, password="short")
    assert r.status_code == 422
    b = r.json()
    assert b["code"] == "VALIDATION_ERROR"
    assert b["details"]["fields"][0]["field"] == "password"
    assert reg(client, email="not-an-email").status_code == 422
    assert reg(client, time_zone="Mars/Base").status_code == 422
    assert reg(client, default_currency="IN").status_code == 422


def test_login_success_and_email_case_insensitive(client):
    reg(client)
    r = client.post("/auth/login", json={"email": "Asha@Example.com", "password": "abcd1234"})
    assert r.status_code == 200
    assert set(r.json()) == {"access_token", "refresh_token", "token_type", "expires_in", "user"}
    assert r.json()["user"]["email"] == "asha@example.com"


def test_login_bad_password_401(client):
    reg(client)
    r = client.post("/auth/login", json={"email": "asha@example.com", "password": "wrongpass"})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_same_error(client):
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "abcd1234"})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


def test_refresh_rotates(client):
    first = reg(client).json()
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert b["refresh_token"] != first["refresh_token"]
    # the new token works
    assert client.post("/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 200


def test_refresh_reuse_revokes_everything(client):
    first = reg(client).json()
    second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    # replay the already-rotated token
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_INVALID"
    # the descendant token is now dead too
    r = client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_INVALID"


def test_refresh_garbage_401(client):
    r = client.post("/auth/refresh", json={"refresh_token": "rt_nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_INVALID"


def test_refresh_expired_401(client, db_session):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from app.models import RefreshToken

    tok = reg(client).json()["refresh_token"]
    db_session.execute(update(RefreshToken).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db_session.commit()
    r = client.post("/auth/refresh", json={"refresh_token": tok})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_INVALID"


def test_refresh_lifetime_is_30_days(client, db_session):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.models import RefreshToken

    reg(client)
    row = db_session.scalar(select(RefreshToken))
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(days=29, hours=23) < delta <= timedelta(days=30)


def test_password_is_argon2_hashed(client, db_session):
    from sqlalchemy import select
    from app.models import User

    reg(client)
    h = db_session.scalar(select(User)).password_hash
    assert h.startswith("$argon2id$")
    assert "abcd1234" not in h
