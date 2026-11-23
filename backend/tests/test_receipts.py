"""S6-B-5: receipt upload and delete (multipart, 10 MB, JPEG/PNG, premium) and the signed file URLs."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app import services_premium
from app.config import settings
from app.models import Receipt
from app.storage import LocalStorage, get_storage
from tests import clock as clockmod
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user

MB = 1024 * 1024
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 100


def jpeg(n):
    return JPEG + b"0" * (n - len(JPEG))


def up(client, who, eid, data=JPEG, ctype="image/jpeg", name="r.jpg", field="file"):
    return client.post(f"/expenses/{eid}/receipt", files={field: (name, data, ctype)}, headers=h(who))


@pytest.fixture()
def setup(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))
    services_premium.grant(db_session, uuid.UUID(uid(a)), period_end=datetime.now(timezone.utc) + timedelta(days=30))
    db_session.commit()
    return a, b, e["id"], gid


def test_4mb_jpeg_is_201_with_a_receipt_url(client, setup):
    a, b, eid, _ = setup
    r = up(client, a, eid, jpeg(4 * MB))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == eid and body["receipt_url"].startswith(settings.storage_public_base_url + "/receipts/")
    assert client.get(f"/expenses/{eid}", headers=h(b)).json()["receipt_url"]  # every participant sees it
    assert client.get(body["receipt_url"]).content == jpeg(4 * MB)             # the signed URL serves the file


def test_11mb_is_413_and_nothing_is_stored(client, db_session, setup):
    a, b, eid, _ = setup
    r = up(client, a, eid, jpeg(11 * MB))
    assert r.status_code == 413 and r.json()["code"] == "VALIDATION_ERROR" and r.json()["details"] == {"max_bytes": 10 * MB}
    assert db_session.scalars(select(Receipt)).all() == []
    assert not list(Path(settings.storage_dir).rglob("*.jpg"))
    assert client.get(f"/expenses/{eid}", headers=h(a)).json()["receipt_url"] is None


def test_exactly_10mb_is_accepted_and_one_byte_more_is_not(client, setup):
    a, b, eid, _ = setup
    assert up(client, a, eid, jpeg(10 * MB)).status_code == 201
    assert up(client, a, eid, jpeg(10 * MB + 1)).status_code == 413


def test_png_is_accepted(client, setup):
    a, _, eid, _ = setup
    r = up(client, a, eid, PNG, "image/png", "r.png")
    assert r.status_code == 201 and ".png" in r.json()["receipt_url"]


@pytest.mark.parametrize("data,ctype", [
    (b"hello", "text/plain"), (b"GIF89a....", "image/gif"), (b"%PDF-1.4", "application/pdf"),
    (PNG, "image/jpeg"), (JPEG, "image/png"), (b"", "image/jpeg"), (b"not an image", "image/jpeg"),
])
def test_wrong_type_or_content_is_422(client, db_session, setup, data, ctype):
    a, _, eid, _ = setup
    r = up(client, a, eid, data, ctype)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["details"]["fields"][0]["field"] == "file"
    assert db_session.scalars(select(Receipt)).all() == []


def test_missing_file_part_is_422(client, setup):
    a, _, eid, _ = setup
    r = up(client, a, eid, field="other")
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    r = client.post(f"/expenses/{eid}/receipt", json={}, headers=h(a))
    assert r.status_code in (400, 422) and r.json()["code"] == "VALIDATION_ERROR"


def test_free_user_upload_is_402(client, db_session, setup):
    a, b, eid, _ = setup  # Ravi is a participant but on the free plan
    r = up(client, b, eid)
    assert r.status_code == 402 and r.json()["code"] == "PREMIUM_REQUIRED" and r.json()["details"] == {"feature": "receipt"}
    assert db_session.scalars(select(Receipt)).all() == []


def test_access_is_checked_before_premium_and_before_the_body(client, setup):
    a, b, eid, _ = setup
    d = user(client, "Dev")
    assert up(client, d, eid).status_code == 403            # a stranger learns nothing about plans
    assert up(client, a, str(uuid.uuid4())).status_code == 404
    assert client.post(f"/expenses/{eid}/receipt", files={"file": ("r.jpg", JPEG, "image/jpeg")}).status_code == 401
    assert client.delete(f"/expenses/{eid}/receipt", headers=h(d)).status_code == 403


def test_upload_to_a_deleted_expense_is_409(client, setup):
    a, _, eid, _ = setup
    client.delete(f"/expenses/{eid}", headers=h(a))
    r = up(client, a, eid)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_DELETED"


def test_a_second_upload_replaces_the_first(client, db_session, setup):
    a, _, eid, _ = setup
    first = up(client, a, eid, JPEG).json()["receipt_url"]
    second = up(client, a, eid, PNG, "image/png", "r.png").json()["receipt_url"]
    assert first.split("?")[0] != second.split("?")[0]
    assert client.get(first).status_code == 404 and client.get(second).content == PNG
    assert len(db_session.scalars(select(Receipt)).all()) == 1
    assert len([p for p in Path(settings.storage_dir).rglob("*") if p.is_file()]) == 1


def test_delete_removes_row_and_file_and_is_idempotent_and_not_gated(client, db_session, setup):
    a, b, eid, _ = setup
    url = up(client, a, eid).json()["receipt_url"]
    assert client.delete(f"/expenses/{eid}/receipt", headers=h(b)).status_code == 204  # free user, but a participant
    assert client.get(url).status_code == 404
    assert client.get(f"/expenses/{eid}", headers=h(a)).json()["receipt_url"] is None
    assert db_session.scalars(select(Receipt)).all() == []
    assert client.delete(f"/expenses/{eid}/receipt", headers=h(a)).status_code == 204
    assert client.delete(f"/expenses/{uuid.uuid4()}/receipt", headers=h(a)).status_code == 404


def test_receipt_url_is_in_lists_too(client, setup):
    a, b, eid, gid = setup
    up(client, a, eid)
    items = client.get(f"/groups/{gid}/expenses", headers=h(b)).json()["items"]
    assert items[0]["receipt_url"]


# ---------- storage and signed URLs ----------
def test_signed_url_must_be_intact_and_unexpired(client, setup, monkeypatch):
    a, _, eid, _ = setup
    clock = clockmod.install(monkeypatch)
    clock.set(0)
    url = up(client, a, eid).json()["receipt_url"]
    assert client.get(url).status_code == 200
    assert client.get(url[:-4] + "0000").status_code == 404                 # wrong signature
    assert client.get(url.replace("exp=", "exp=9")).status_code == 404      # tampered expiry
    path = url.split("?")[0]
    assert client.get(path).status_code == 422                             # unsigned (query params required)
    clock.set(settings.receipt_url_seconds - 1)
    assert client.get(url).status_code == 200
    clock.set(settings.receipt_url_seconds + 5)
    assert client.get(url).status_code == 404
    assert client.get(f"/expenses/{eid}", headers=h(a)).json()["receipt_url"] != url  # a fresh URL on every read


def test_storage_refuses_keys_that_escape_the_root(tmp_path):
    s = LocalStorage(str(tmp_path))
    for bad in ("../x", "a/../../x", "/etc/passwd", "", "a/..", "x y"):
        with pytest.raises(ValueError):
            s.put(bad, b"x")
    s.put("ok/one.bin", b"1")
    assert s.read("ok/one.bin") == b"1" and s.exists("ok/one.bin")
    s.delete("ok/one.bin")
    s.delete("ok/one.bin")  # deleting twice is fine
    assert not s.exists("ok/one.bin")


def test_files_route_is_not_part_of_the_contract(client):
    from app.main import app
    assert not any(p.startswith("/files") for p in app.openapi()["paths"])
    assert client.get("/files/receipts/x.jpg", params={"exp": 9999999999, "sig": "00"}).status_code == 404
