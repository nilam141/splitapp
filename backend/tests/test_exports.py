"""S6-B-7: export jobs. POST /exports (premium), GET /exports/{id} with a fresh 15-minute signed URL, 24 h purge."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app import scheduler, services_exports, services_premium
from app.config import settings
from app.models import Export, User
from app.schemas_exports import ExportCreate
from tests import clock as clockmod
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user

HOUR = 3600


@pytest.fixture()
def clock(monkeypatch):
    return clockmod.install(monkeypatch)


def premium(db, u):
    services_premium.grant(db, uuid.UUID(uid(u)), period_end=datetime.now(timezone.utc) + timedelta(days=365))
    db.commit()


@pytest.fixture()
def g(client, db_session):
    """Group "Flat 4B" with 3 expenses and 1 payment. Nets: Asha +38000, Ravi -2000, Meera -36000."""
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c], name="Flat 4B")
    create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=90000, description="Dinner", date="2026-11-01"))
    create_group_expense(client, b, gid, equal_body(b, [a, b, c], total=30000, description="Taxi", date="2026-11-02"))
    create_group_expense(client, c, gid, equal_body(c, [a, b, c], total=6000, description="Snacks", date="2026-11-03"))
    pay = {"group_id": gid, "from_user_id": uid(b), "to_user_id": uid(a), "amount": {"amount_minor": 10000, "currency": "INR"},
           "settled_on": "2026-11-04"}
    assert client.post("/settlements", json=pay, headers=h(b)).status_code == 201
    premium(db_session, a)
    return a, b, c, gid


def start(client, who, **body):
    return client.post("/exports", json=body, headers=h(who))


def poll(client, who, eid):
    return client.get(f"/exports/{eid}", headers=h(who))


def csv_of(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.text


def test_group_export_is_a_csv_with_six_lines(client, g):
    a, b, c, gid = g
    r = start(client, a, scope="group", group_id=gid)
    assert r.status_code == 202
    first = r.json()
    assert first["status"] == "pending" and first["scope"] == "group" and first["format"] == "csv"
    assert first["download_url"] is None and first["file_name"] is None and first["expires_at"] is None
    got = poll(client, a, first["id"]).json()
    assert got["status"] == "ready" and got["id"] == first["id"] and got["created_at"] == first["created_at"]
    assert got["file_name"].startswith("flat-4b-") and got["file_name"].endswith(".csv")
    text = csv_of(client, got["download_url"])
    lines = text.splitlines()
    assert len(lines) == 6  # header + 3 expenses + 1 payment + 1 total row
    assert lines == [
        "date,description,category,cost,currency,Asha,Ravi,Meera",
        "2026-11-01,Dinner,Uncategorized,900.00,INR,600.00,-300.00,-300.00",
        "2026-11-02,Taxi,Uncategorized,300.00,INR,-100.00,200.00,-100.00",
        "2026-11-03,Snacks,Uncategorized,60.00,INR,-20.00,-20.00,40.00",
        "2026-11-04,Payment: Ravi paid Asha,Payment,100.00,INR,-100.00,100.00,0.00",
        ",Total,,,INR,380.00,-20.00,-360.00"]


def test_ninety_thousand_inr_renders_as_900_00(client, g):
    a, _, _, gid = g
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    assert "900.00" in csv_of(client, poll(client, a, eid).json()["download_url"])


def test_deleted_expenses_and_payments_are_left_out(client, db_session, g):
    a, b, c, gid = g
    items = client.get(f"/groups/{gid}/expenses", headers=h(a)).json()["items"]
    client.delete(f"/expenses/{next(i['id'] for i in items if i['description'] == 'Taxi')}", headers=h(a))
    sid = client.get("/settlements", headers=h(a)).json()["items"][0]["id"]
    client.delete(f"/settlements/{sid}", headers=h(a))
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    lines = csv_of(client, poll(client, a, eid).json()["download_url"]).splitlines()
    assert len(lines) == 1 + 2 + 1 and not any("Taxi" in l or "Payment" in l for l in lines)


def test_two_currencies_get_a_total_row_each(client, g):
    a, b, c, gid = g
    create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=900, currency="JPY", description="Ramen", date="2026-11-05"))
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    lines = csv_of(client, poll(client, a, eid).json()["download_url"]).splitlines()
    assert lines[-2].endswith("380.00,-20.00,-360.00") and lines[-1] == ",Total,,,JPY,600,-300,-300"
    assert "2026-11-05,Ramen,Uncategorized,900,JPY,600,-300,-300" in lines


def test_friend_export_has_two_member_columns(client, g):
    a, b, c, gid = g
    eid = start(client, a, scope="friend", friend_user_id=uid(b)).json()["id"]
    got = poll(client, a, eid).json()
    assert got["status"] == "ready" and got["scope"] == "friend" and got["file_name"].startswith("ravi-")
    lines = csv_of(client, got["download_url"]).splitlines()
    assert lines[0] == "date,description,category,cost,currency,Asha,Ravi"
    # the group rows the two share (Dinner, Taxi, Snacks) plus the payment between them, then the totals
    assert lines[1:] == ["2026-11-01,Dinner,Uncategorized,900.00,INR,600.00,-300.00",
                         "2026-11-02,Taxi,Uncategorized,300.00,INR,-100.00,200.00",
                         "2026-11-03,Snacks,Uncategorized,60.00,INR,-20.00,-20.00",
                         "2026-11-04,Payment: Ravi paid Asha,Payment,100.00,INR,-100.00,100.00",
                         ",Total,,,INR,380.00,-20.00"]


def test_each_poll_issues_a_fresh_15_minute_url(client, g, clock):
    a, _, _, gid = g
    clock.set(0)
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    p1 = poll(client, a, eid).json()
    clock.set(300)
    p2 = poll(client, a, eid).json()
    assert p1["download_url"] != p2["download_url"]
    e1, e2 = (int(parse_qs(urlsplit(p["download_url"]).query)["exp"][0]) for p in (p1, p2))
    assert e2 - e1 == 300 and e1 == int(clock.base.timestamp()) + 900
    assert datetime.fromisoformat(p2["expires_at"]) - datetime.fromisoformat(p1["expires_at"]) == timedelta(seconds=300)
    assert client.get(p1["download_url"]).status_code == 200
    clock.set(901)          # p1 expired at 900, p2 (issued at 300) is valid until 1200
    assert client.get(p1["download_url"]).status_code == 404
    assert client.get(p2["download_url"]).status_code == 200
    p3 = poll(client, a, eid).json()
    assert client.get(p3["download_url"]).status_code == 200


def test_file_is_gone_after_24h_and_the_export_is_404(client, db_session, g, clock):
    a, _, _, gid = g
    clock.set(0)
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    url = poll(client, a, eid).json()["download_url"]
    files = [p for p in Path(settings.storage_dir).rglob("*.csv")]
    assert len(files) == 1
    clock.set(24 * HOUR - 60)
    assert poll(client, a, eid).status_code == 200 and files[0].exists()
    clock.set(24 * HOUR + 1)
    assert poll(client, a, eid).status_code == 404
    assert not files[0].exists() and not list(Path(settings.storage_dir).rglob("*.csv"))
    assert client.get(url).status_code == 404
    db_session.expire_all()
    assert db_session.scalars(select(Export)).all() == []


def test_the_scheduler_purges_expired_exports_without_a_poll(client, db_session, g, clock):
    a, _, _, gid = g
    clock.set(0)
    start(client, a, scope="group", group_id=gid)
    start(client, a, scope="group", group_id=gid)
    assert len(list(Path(settings.storage_dir).rglob("*.csv"))) == 2
    clock.set(24 * HOUR - 1)
    assert scheduler.run_once(db_session)["exports_purged"] == 0
    clock.set(24 * HOUR + 1)
    assert scheduler.run_once(db_session)["exports_purged"] == 2
    assert not list(Path(settings.storage_dir).rglob("*.csv"))


def test_pending_exports_are_picked_up_by_the_scheduler(client, db_session, g):
    a, _, _, gid = g
    ex = services_exports.create_export(db_session, db_session.get(User, uuid.UUID(uid(a))),
                                        ExportCreate(scope="group", group_id=uuid.UUID(gid)))
    assert ex.status == "pending"  # nobody ran the background task (as after a crash)
    assert scheduler.run_once(db_session)["exports_generated"] == 1
    assert poll(client, a, str(ex.id)).json()["status"] == "ready"


def test_a_failing_build_marks_the_export_failed(client, g, monkeypatch):
    a, _, _, gid = g

    def boom(*args):
        raise RuntimeError("disk full")

    monkeypatch.setattr(services_exports, "_rows_for", boom)
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    got = poll(client, a, eid).json()
    assert got["status"] == "failed" and got["download_url"] is None and got["file_name"] is None and got["expires_at"] is None


# ---------- guards ----------
def test_free_user_export_is_402(client, g):
    a, b, c, gid = g
    r = start(client, b, scope="group", group_id=gid)
    assert r.status_code == 402 and r.json()["code"] == "PREMIUM_REQUIRED" and r.json()["details"] == {"feature": "export"}


def test_export_access_rules(client, db_session, g):
    a, b, c, gid = g
    d = user(client, "Dev")
    premium(db_session, d)
    assert start(client, d, scope="group", group_id=gid).status_code == 403            # not a member
    assert start(client, a, scope="group", group_id=str(uuid.uuid4())).status_code == 404
    assert start(client, d, scope="friend", friend_user_id=uid(a)).status_code == 403  # not friends
    assert start(client, a, scope="group").status_code == 422
    assert start(client, a, scope="friend").status_code == 422
    assert start(client, a, scope="team", group_id=gid).status_code == 422
    assert start(client, a, scope="group", group_id=gid, format="xlsx").status_code == 422
    assert client.post("/exports", json={"scope": "group", "group_id": gid}).status_code == 401
    # a member who left cannot export
    client.delete(f"/groups/{gid}/members/me", headers=h(c))


def test_an_export_belongs_to_the_person_who_asked(client, db_session, g):
    a, b, c, gid = g
    eid = start(client, a, scope="group", group_id=gid).json()["id"]
    premium(db_session, b)
    assert poll(client, b, eid).status_code == 404
    assert poll(client, a, str(uuid.uuid4())).status_code == 404
    assert client.get(f"/exports/{eid}").status_code == 401
    assert poll(client, a, "not-a-uuid").status_code == 422


def test_left_member_cannot_export_the_group(client, db_session, g):
    a, b, c, gid = g
    pay = {"group_id": gid, "from_user_id": uid(c), "to_user_id": uid(a), "amount": {"amount_minor": 36000, "currency": "INR"}, "settled_on": "2026-11-06"}
    assert client.post("/settlements", json=pay, headers=h(c)).status_code == 201
    assert client.delete(f"/groups/{gid}/members/me", headers=h(c)).status_code == 204
    premium(db_session, c)
    assert start(client, c, scope="group", group_id=gid).status_code == 403
