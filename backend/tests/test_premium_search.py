"""S6-B-6: plan on /users/me and the 402 guard; `GET /expenses?q=` search (premium)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import services_premium
from app.models import Subscription
from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user

NOW = datetime.now(timezone.utc)


def make_premium(db, u, **kw):
    kw.setdefault("period_end", NOW + timedelta(days=30))
    services_premium.grant(db, uuid.UUID(uid(u)), **kw)
    db.commit()


def me(client, u):
    return client.get("/users/me", headers=h(u)).json()


def test_plan_on_users_me(client, db_session):
    a = user(client, "Asha")
    assert (me(client, a)["plan"], me(client, a)["premium_until"]) == ("free", None)
    end = NOW + timedelta(days=30)
    make_premium(db_session, a, period_end=end)
    got = me(client, a)
    assert got["plan"] == "premium"
    until = datetime.fromisoformat(got["premium_until"])
    if until.tzinfo is None:  # SQLite returns naive UTC
        until = until.replace(tzinfo=timezone.utc)
    assert abs((until - end).total_seconds()) < 1
    assert client.patch("/users/me", json={"name": "Asha K"}, headers=h(a)).json()["plan"] == "premium"


@pytest.mark.parametrize("kw,plan", [
    ({"status": "grace"}, "premium"),
    ({"plan": "premium_yearly", "period_end": None}, "premium"),
    ({"status": "expired"}, "free"), ({"status": "cancelled"}, "free"),
    ({"period_end": NOW - timedelta(seconds=1)}, "free"), ({"plan": "free"}, "free"),
])
def test_entitlement_rules(client, db_session, kw, plan):
    a = user(client, "Asha")
    make_premium(db_session, a, **kw)
    got = me(client, a)
    assert got["plan"] == plan
    if plan == "free":
        assert got["premium_until"] is None


def test_free_user_search_is_402(client):
    a = user(client, "Asha")
    r = client.get("/expenses", params={"q": "goa"}, headers=h(a))
    assert r.status_code == 402 and r.json()["code"] == "PREMIUM_REQUIRED" and r.json()["details"] == {"feature": "search"}
    assert client.get("/expenses", headers=h(a)).status_code == 200  # the plain list stays free
    assert client.get("/expenses", params={"q": "g"}, headers=h(a)).status_code == 422  # validation first


def test_premium_search_returns_exactly_the_match(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    create_group_expense(client, a, gid, equal_body(a, [a, b], description="Dinner Goa"))
    create_group_expense(client, a, gid, equal_body(a, [a, b], description="Groceries"))
    make_premium(db_session, a)
    r = client.get("/expenses", params={"q": "goa"}, headers=h(a))
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["description"] for i in items] == ["Dinner Goa"] and r.json()["next_cursor"] is None
    assert [i["description"] for i in client.get("/expenses", params={"q": "GOA"}, headers=h(a)).json()["items"]] == ["Dinner Goa"]
    assert client.get("/expenses", params={"q": "zzz"}, headers=h(a)).json()["items"] == []


def test_search_covers_notes_and_escapes_wildcards(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    create_group_expense(client, a, gid, {**equal_body(a, [a, b], description="Taxi"), "notes": "airport run"})
    create_group_expense(client, a, gid, equal_body(a, [a, b], description="100% juice"))
    create_group_expense(client, a, gid, equal_body(a, [a, b], description="a_b"))
    make_premium(db_session, a)
    names = lambda q: sorted(i["description"] for i in client.get("/expenses", params={"q": q}, headers=h(a)).json()["items"])
    assert names("AIRPORT") == ["Taxi"]
    assert names("0% j") == ["100% juice"]
    assert names("%%") == []          # not "match everything"
    assert names("a_") == ["a_b"] and names("_b") == ["a_b"]


def test_search_by_amount_uses_the_currencys_own_exponent(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=90000, description="Hotel"))                 # 900.00 INR
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=900, description="Snack"))                   # 9.00 INR
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=900, currency="JPY", description="Ramen"))   # 900 JPY
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=90050, description="Cab"))                  # 900.50 INR
    make_premium(db_session, a)
    names = lambda q: sorted(i["description"] for i in client.get("/expenses", params={"q": q}, headers=h(a)).json()["items"])
    assert names("900") == ["Hotel", "Ramen"]
    assert names("900.00") == ["Hotel"]          # JPY has no decimals, so "900.00" cannot be 900 JPY
    assert names("900.0") == ["Hotel"]
    assert names("900.5") == ["Cab"] and names("900.50") == ["Cab"]
    assert names("9.00") == ["Snack"] and names("9.0") == ["Snack"]
    assert names("900.505") == []                # more decimals than any currency here has


def test_search_only_sees_the_callers_expenses_and_pages(client, db_session):
    a, b, d = user(client, "Asha"), user(client, "Ravi"), user(client, "Dev")
    g1, g2 = make_group(client, a, [b]), make_group(client, d, [])
    for i in range(3):
        create_group_expense(client, a, g1, equal_body(a, [a, b], description=f"Goa trip {i}", date=f"2026-11-0{i + 1}"))
    create_group_expense(client, d, g2, {**equal_body(d, [d]), "description": "Goa secret"})
    make_premium(db_session, a)
    first = client.get("/expenses", params={"q": "goa", "limit": 2}, headers=h(a)).json()
    assert [i["description"] for i in first["items"]] == ["Goa trip 2", "Goa trip 1"] and first["next_cursor"]
    second = client.get("/expenses", params={"q": "goa", "limit": 2, "cursor": first["next_cursor"]}, headers=h(a)).json()
    assert [i["description"] for i in second["items"]] == ["Goa trip 0"] and second["next_cursor"] is None


def test_search_stops_when_the_subscription_lapses(client, db_session):
    a = user(client, "Asha")
    make_premium(db_session, a)
    assert client.get("/expenses", params={"q": "ab"}, headers=h(a)).status_code == 200
    sub = db_session.get(Subscription, uuid.UUID(uid(a)))
    sub.current_period_end = NOW - timedelta(minutes=1)
    db_session.commit()
    assert client.get("/expenses", params={"q": "ab"}, headers=h(a)).status_code == 402
