"""Refresh-rotation race, secret guard, and error mapping."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import services_auth
from app.config import DEV_JWT_SECRET, Settings
from app.errors import ApiError, install_error_handlers
from app.models import RefreshToken

from tests.test_auth import reg


def test_refresh_lost_race_is_treated_as_reuse(client, engine):
    """Request A passes the revoked_at check; request B rotates the same token before A's UPDATE runs."""
    data = reg(client).json()
    raw = data["refresh_token"]
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as a, factory() as b:
        orig_get = a.get

        def racing_get(*args, **kwargs):
            result = orig_get(*args, **kwargs)  # A has already read the row with revoked_at NULL
            services_auth.refresh(b, raw)  # B wins the rotation
            return result

        a.get = racing_get
        with pytest.raises(ApiError) as e:
            services_auth.refresh(a, raw)
        assert e.value.status == 401 and e.value.code == "TOKEN_INVALID"

    with factory() as s:
        rows = s.scalars(select(RefreshToken)).all()
        assert len(rows) == 2  # the original and B's rotation; nothing issued to A
        assert all(r.revoked_at is not None for r in rows)  # reuse revoked every live token


def test_jwt_secret_default_refused_in_production():
    with pytest.raises(ValidationError):
        Settings(env="production", jwt_secret=DEV_JWT_SECRET)
    with pytest.raises(ValidationError):
        Settings(env="PROD", jwt_secret=DEV_JWT_SECRET)
    assert Settings(env="production", jwt_secret="x" * 48).env == "production"
    assert Settings(env="development", jwt_secret=DEV_JWT_SECRET).jwt_secret == DEV_JWT_SECRET


def test_unknown_route_and_method_use_error_envelope(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    r = client.delete("/currencies")
    assert r.status_code == 405
    body = r.json()
    assert body["code"] == "NOT_IMPLEMENTED" and set(body) == {"code", "message"}


def test_status_mapping_other_codes():
    app = FastAPI()
    install_error_handlers(app)
    from fastapi import HTTPException

    @app.get("/{status}")
    def boom(status: int):
        raise HTTPException(status)

    c = TestClient(app)
    expect = {400: "VALIDATION_ERROR", 413: "VALIDATION_ERROR", 429: "RATE_LIMITED", 403: "FORBIDDEN",
              401: "TOKEN_INVALID", 503: "INTERNAL_ERROR"}
    for status, code in expect.items():
        r = c.get(f"/{status}")
        assert r.status_code == status and r.json()["code"] == code


def test_unhandled_exception_returns_generic_500():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail /etc/passwd")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json() == {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    assert "secret" not in r.text and "Traceback" not in r.text
