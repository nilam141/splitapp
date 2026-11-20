"""S1-Q-1: GET /currencies against the Currency schema and seed requirements."""
import re

from sqlalchemy import text


def test_seed_at_least_30_and_known_exponents(client):
    items = client.get("/currencies").json()
    assert len(items) >= 30
    by = {c["code"]: c for c in items}
    assert (by["INR"]["exponent"], by["JPY"]["exponent"], by["KWD"]["exponent"], by["USD"]["exponent"]) == (2, 0, 3, 2)
    for code in ("EUR", "GBP", "AUD", "CAD", "SGD", "AED"):
        assert code in by


def test_every_item_matches_currency_schema(client):
    for c in client.get("/currencies").json():
        assert set(c) == {"code", "name", "symbol", "exponent"}
        assert re.fullmatch(r"[A-Z]{3}", c["code"])
        assert isinstance(c["name"], str) and c["name"]
        assert isinstance(c["symbol"], str) and c["symbol"]
        assert type(c["exponent"]) is int and 0 <= c["exponent"] <= 4


def test_response_is_bare_array_json_and_idempotent(client):
    r = client.get("/currencies")
    assert r.headers["content-type"].startswith("application/json")
    assert isinstance(r.json(), list)
    assert client.get("/currencies").json() == r.json()


def test_register_accepts_every_seeded_currency(client):
    codes = [c["code"] for c in client.get("/currencies").json()]
    for i, code in enumerate(codes):
        r = client.post("/auth/register", json={"email": f"u{i}@example.com", "password": "abcd1234",
                                                "name": "U", "default_currency": code})
        assert r.status_code == 201, code
        assert r.json()["user"]["default_currency"] == code


def test_db_seed_rows(db_session):
    n = db_session.execute(text("select count(*) from currencies")).scalar()
    assert n >= 30
