"""S2-Q-1: every Slice 1 and Slice 2 endpoint response validates against docs/openapi.yaml.

Each call goes through `call()`, which sends the request with the FastAPI test client and then validates the real
response (status code, headers, JSON body) against the operation in the spec with openapi-core. Success and the
documented error paths are both exercised, so an undocumented status code or a body that does not match its schema
fails the test. Requests are validated too, so a test cannot drift from the contract.

Operations from Slice 1 and Slice 2 that exist in the spec but have no route yet (groups/join, restore, invite-link) are listed in NOT_YET_IMPLEMENTED and checked to still be absent from the app, so the coverage test fails
as soon as one ships without a contract test.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import jsonschema
import pytest
import yaml
from openapi_core import OpenAPI
from openapi_core.validation.request.exceptions import SecurityValidationError
from openapi_core.templating.responses.exceptions import ResponseNotFound
from openapi_core.testing import MockRequest, MockResponse
from sqlalchemy import select

from app.main import app
from app.models import Notification

from tests.test_auth import reg

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = OpenAPI.from_file_path(str(SPEC_PATH))
_DOC = yaml.safe_load(SPEC_PATH.read_text())
RAW = _DOC["paths"]

# Operations in scope for Slice 1 + Slice 2 (operationId -> (method, path template)).
IN_SCOPE = {
    ("get", "/health"), ("post", "/auth/register"), ("post", "/auth/login"), ("post", "/auth/refresh"),
    ("post", "/auth/logout"), ("post", "/auth/password-reset"), ("post", "/auth/password-reset/confirm"),
    ("get", "/users/me"), ("patch", "/users/me"),
    ("get", "/friends"), ("post", "/friends"), ("get", "/friends/{user_id}"), ("delete", "/friends/{user_id}"),
    ("get", "/groups"), ("post", "/groups"), ("get", "/groups/{id}"), ("patch", "/groups/{id}"),
    ("delete", "/groups/{id}"), ("post", "/groups/{id}/members"), ("delete", "/groups/{id}/members/{user_id}"),
    ("get", "/categories"), ("get", "/currencies"),
    # Slice 3
    ("get", "/groups/{id}/timeline"),
    ("get", "/groups/{id}/expenses"), ("post", "/groups/{id}/expenses"),
    ("get", "/expenses"), ("post", "/expenses"), ("get", "/expenses/{id}"), ("patch", "/expenses/{id}"),
    ("delete", "/expenses/{id}"), ("post", "/expenses/{id}/restore"),
    ("get", "/expenses/{id}/comments"), ("post", "/expenses/{id}/comments"),
}
# In the spec under the Slice 2 heading but not in any S2-B task (no route yet).
NOT_YET_IMPLEMENTED = {
    ("post", "/groups/join"), ("post", "/groups/{id}/restore"), ("get", "/groups/{id}/invite-link"),
    ("post", "/groups/{id}/invite-link"),
}

COVERED: set[tuple[str, str]] = set()


def _template(method, path):
    """Spec path template for a concrete path; a literal template beats a parameterised one."""
    path = path.split("?")[0]
    hits = [tpl for tpl, item in RAW.items() if method.lower() in item
            and re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", tpl), path)]
    assert hits, f"{method} {path} is not in the spec"
    return min(hits, key=lambda t: t.count("{"))


_NAIVE_TS = re.compile(rb'"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)"')


def _tz_for_sqlite(body: bytes) -> bytes:
    """SQLite returns naive datetimes (no zone), PostgreSQL timestamptz returns an offset. The contract says
    date-time (RFC 3339, offset required), so on SQLite only, mark naive timestamps as UTC before validating.
    The Postgres run validates the real output."""
    return _NAIVE_TS.sub(rb'"\1Z"', body)


class Caller:
    def __init__(self, client):
        self.client = client

    def __call__(self, method, path, expect, token=None, json_body=None, headers=None, params=None):
        h = dict(headers or {})
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = self.client.request(method, path, json=json_body, headers=h, params=params)
        assert r.status_code == expect, f"{method} {path}: wanted {expect}, got {r.status_code} {r.text}"
        body = r.content or b""
        ctype = r.headers.get("content-type", "")
        mreq = MockRequest(
            "http://localhost:8000", method.lower(), path, args=params or {},
            headers={k: v for k, v in h.items()},
            content_type="application/json" if json_body is not None else "",
            data=json.dumps(json_body).encode() if json_body is not None else b"",
        )
        if not os.environ.get("TEST_DATABASE_URL") and body:
            body = _tz_for_sqlite(body)
        mresp = MockResponse(body, status_code=r.status_code, headers=dict(r.headers),
                             content_type=ctype.split(";")[0] if body else "")
        try:
            if expect != 422:  # 422 cases send deliberately invalid bodies
                SPEC.validate_request(mreq)
        except SecurityValidationError:
            # Only the deliberate no-token calls may lack credentials; the API must answer those with 401.
            assert token is None and r.status_code == 401, "request lacked credentials but was not a 401 case"
        try:
            SPEC.validate_response(mreq, mresp)
        except ResponseNotFound:
            # openapi.yaml info section: every bearer-protected operation can also return 401 and 5xx, "not repeated
            # on each operation". Accept an undeclared 401 only if its body is the documented Error schema.
            assert r.status_code == 401, f"{method} {path}: status {r.status_code} is not documented"
            jsonschema.validate(r.json(), {"$ref": "#/components/schemas/Error", "components": _DOC["components"]})
            assert r.json()["code"] in ("TOKEN_EXPIRED", "TOKEN_INVALID")
        COVERED.add((method.lower(), _template(method, path)))
        return r


@pytest.fixture()
def call(client):
    return Caller(client)


def _bearer(d):
    return d["access_token"]


def test_health_and_reference_data(call):
    call("GET", "/health", 200)
    call("GET", "/currencies", 200)
    call("GET", "/categories", 200)


def test_auth_endpoints(call, client, db_session):
    reg_body = {"email": "asha@example.com", "password": "abcd1234", "name": "Asha"}
    a = call("POST", "/auth/register", 201, json_body=reg_body).json()
    call("POST", "/auth/register", 409, json_body=reg_body)
    call("POST", "/auth/register", 422, json_body={"email": "bad", "password": "x", "name": ""})
    call("POST", "/auth/login", 200, json_body={"email": "asha@example.com", "password": "abcd1234"})
    call("POST", "/auth/login", 401, json_body={"email": "asha@example.com", "password": "wrong-pass1"})
    t = call("POST", "/auth/refresh", 200, json_body={"refresh_token": a["refresh_token"]}).json()
    call("POST", "/auth/refresh", 401, json_body={"refresh_token": "rt_unknown"})
    call("POST", "/auth/logout", 204, token=t["access_token"], json_body={"refresh_token": t["refresh_token"]})
    call("POST", "/auth/logout", 401, json_body={"refresh_token": t["refresh_token"]})
    call("POST", "/auth/password-reset", 202, json_body={"email": "asha@example.com"})
    tok = db_session.scalars(select(Notification).where(Notification.type == "password_reset")).all()[-1].payload["token"]
    call("POST", "/auth/password-reset/confirm", 200, json_body={"token": tok, "new_password": "newpass99"})
    call("POST", "/auth/password-reset/confirm", 410, json_body={"token": tok, "new_password": "newpass99"})


def test_login_rate_limit_response_matches_contract(call):
    reg_user(call.client, "limit@example.com", "Limit")
    for _ in range(5):
        call("POST", "/auth/login", 401, json_body={"email": "limit@example.com", "password": "wrong-pass1"})
    r = call("POST", "/auth/login", 429, json_body={"email": "limit@example.com", "password": "abcd1234"})
    assert r.headers["Retry-After"] == str(r.json()["details"]["retry_after_seconds"])


def test_users_me(call):
    a = reg_user(call.client)
    call("GET", "/users/me", 200, token=_bearer(a))
    call("GET", "/users/me", 401)
    call("PATCH", "/users/me", 200, token=_bearer(a),
         json_body={"default_currency": "USD", "notification_prefs": {"comment_added": False}})
    call("PATCH", "/users/me", 422, token=_bearer(a), json_body={"default_currency": "ZZZ"})
    other = reg_user(call.client, "ravi@example.com", "Ravi")
    call("PATCH", "/users/me", 409, token=_bearer(a), json_body={"email": other["user"]["email"]})


def reg_user(client, email="asha@example.com", name="Asha"):
    return reg(client, email=email, name=name).json()


def test_friends(call):
    a, b = reg_user(call.client), reg_user(call.client, "ravi@example.com", "Ravi")
    ta = _bearer(a)
    call("GET", "/friends", 200, token=ta)
    call("GET", "/friends", 401)
    for f in ("all", "outstanding", "owes_me", "i_owe"):
        call("GET", "/friends", 200, token=ta, params={"filter": f})
    call("POST", "/friends", 201, token=ta, json_body={"email": "ravi@example.com"})
    call("POST", "/friends", 200, token=ta, json_body={"email": "ravi@example.com"})
    call("POST", "/friends", 201, token=ta, json_body={"email": "new@example.com", "name": "New Person"})  # placeholder
    call("POST", "/friends", 422, token=ta, json_body={"email": "asha@example.com"})  # self
    call("POST", "/friends", 422, token=ta, json_body={})
    call("POST", "/friends", 401, json_body={"email": "x@example.com"})
    call("GET", f"/friends/{b['user']['id']}", 200, token=ta)
    call("GET", "/friends/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff", 404, token=ta)
    call("DELETE", f"/friends/{b['user']['id']}", 204, token=ta)
    call("DELETE", f"/friends/{b['user']['id']}", 404, token=ta)
    # 409 SHARED_GROUPS_EXIST
    c = reg_user(call.client, "meera@example.com", "Meera")
    call("POST", "/groups", 201, token=ta, json_body={"name": "G", "member_user_ids": [c["user"]["id"]]})
    call("GET", f"/friends/{c['user']['id']}", 200, token=ta)  # implicit friend
    call("DELETE", f"/friends/{c['user']['id']}", 409, token=ta)


def test_groups(call):
    a, b, c = (reg_user(call.client, f"{n.lower()}@example.com", n) for n in ("Asha", "Ravi", "Meera"))
    ta, tb, tc = _bearer(a), _bearer(b), _bearer(c)
    call("GET", "/groups", 200, token=ta)
    call("GET", "/groups", 401)
    g = call("POST", "/groups", 201, token=ta, headers={"Idempotency-Key": "0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1a0001"},
             json_body={"name": "Goa Trip", "group_type": "trip", "trip_start_date": "2026-12-20",
                        "trip_end_date": "2026-12-27", "member_user_ids": [b["user"]["id"]],
                        "new_members": [{"name": "Kiran", "email": "kiran@example.com"}]}).json()
    call("POST", "/groups", 201, token=ta, headers={"Idempotency-Key": "0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1a0001"},
         json_body={"name": "Goa Trip", "group_type": "trip", "trip_start_date": "2026-12-20",
                    "trip_end_date": "2026-12-27", "member_user_ids": [b["user"]["id"]],
                    "new_members": [{"name": "Kiran", "email": "kiran@example.com"}]})
    call("POST", "/groups", 422, token=ta, json_body={"name": ""})
    call("POST", "/groups", 422, token=ta, json_body={"name": "X", "trip_start_date": "2026-12-20",
                                                      "trip_end_date": "2026-12-01"})
    call("POST", "/groups", 401, json_body={"name": "X"})
    gid = g["id"]
    call("GET", f"/groups/{gid}", 200, token=ta)
    call("GET", f"/groups/{gid}", 403, token=tc)
    call("GET", "/groups/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff", 404, token=ta)
    p = call("PATCH", f"/groups/{gid}", 200, token=tb,
             json_body={"version": 1, "name": "Flat", "simplify_debts": False, "whiteboard": "hi"}).json()
    call("PATCH", f"/groups/{gid}", 409, token=ta, json_body={"version": 1, "name": "Stale"})
    call("PATCH", f"/groups/{gid}", 403, token=tc, json_body={"version": p["version"], "name": "No"})
    call("PATCH", f"/groups/{gid}", 422, token=ta, json_body={"name": "no version"})
    call("POST", f"/groups/{gid}/members", 200, token=ta,
         json_body={"user_ids": [c["user"]["id"]], "new_members": [{"name": "Lee", "phone_e164": "+919800000001"}]})
    call("POST", f"/groups/{gid}/members", 403, token=_bearer(reg_user(call.client, "z@example.com", "Zed")),
         json_body={"user_ids": []})
    call("POST", f"/groups/{gid}/members", 422, token=ta, json_body={"user_ids": ["not-a-uuid"]})
    call("DELETE", f"/groups/{gid}/members/{c['user']['id']}", 204, token=ta)
    call("DELETE", f"/groups/{gid}/members/{c['user']['id']}", 404, token=ta)
    call("DELETE", f"/groups/{gid}/members/{b['user']['id']}", 403, token=tc)
    call("DELETE", f"/groups/{gid}/members/me", 204, token=tb)
    call("DELETE", f"/groups/{gid}", 403, token=tc)
    call("DELETE", f"/groups/{gid}", 204, token=ta)
    call("DELETE", f"/groups/{gid}", 409, token=ta)


def _norm(path: str) -> str:
    """FastAPI names path parameters after the handler argument ({group_id}); the spec says {id}. Compare by shape."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def shipped_operations(application) -> set[tuple[str, str]]:
    """(method, path template) of every operation the app serves. Walks the generated OpenAPI document, which
    includes routes of nested/included routers (they are not all visible in `app.routes`)."""
    doc = application.openapi()
    return {(m, _norm(p)) for p, item in doc["paths"].items() for m in item
            if m in ("get", "post", "put", "patch", "delete")}


def test_shipped_guard_negative_control():
    """The guard must see routes added through included routers, including nested ones, and must flag an unlisted one."""
    from fastapi import APIRouter, FastAPI
    inner, outer = APIRouter(), APIRouter()

    @inner.get("/widgets/{wid}/spin")
    def spin(wid: str):  # pragma: no cover
        return {}

    outer.include_router(inner, prefix="/v2")
    probe = FastAPI()
    probe.include_router(outer)
    ops = shipped_operations(probe)
    unlisted = ops - {(m, _norm(p)) for m, p in IN_SCOPE | NOT_YET_IMPLEMENTED}
    assert unlisted == {("get", "/v2/widgets/{}/spin")}
    # and the real app is visible to it (it was blind with app.routes)
    real = shipped_operations(app)
    assert ("get", "/groups/{}/timeline") in real and ("post", "/expenses/{}/comments") in real
    # a route that was listed as not yet implemented is reported once it is served
    probe2 = FastAPI()
    probe2.include_router(APIRouter(prefix="/groups"))
    r = APIRouter()
    r.add_api_route("/groups/join", lambda: {}, methods=["POST"])
    probe2.include_router(r)
    assert {(m, _norm(p)) for m, p in NOT_YET_IMPLEMENTED} & shipped_operations(probe2) == {("post", "/groups/join")}


def test_validator_rejects_a_response_that_breaks_the_contract(client):
    """Negative control: the machinery above must fail on a wrong body and on an undocumented status."""
    from openapi_core.exceptions import OpenAPIError
    from openapi_core.validation.response.exceptions import InvalidData
    req = MockRequest("http://localhost:8000", "get", "/currencies")
    good = json.dumps([{"code": "INR", "name": "Indian Rupee", "symbol": "Rs", "exponent": 2}]).encode()
    SPEC.validate_response(req, MockResponse(good, status_code=200, content_type="application/json"))
    bad = json.dumps([{"code": "INR", "name": "Indian Rupee", "symbol": "Rs", "exponent": "two"}]).encode()
    with pytest.raises(InvalidData):
        SPEC.validate_response(req, MockResponse(bad, status_code=200, content_type="application/json"))
    with pytest.raises(OpenAPIError):
        SPEC.validate_response(req, MockResponse(b"{}", status_code=418, content_type="application/json"))


# ---- Slice 3: expenses, comments, timeline ------------------------------------------------------------------------

def _people(call):
    a, b, c = (reg_user(call.client, f"{n.lower()}@example.com", n) for n in ("Asha", "Ravi", "Meera"))
    g = call("POST", "/groups", 201, token=_bearer(a), json_body={"name": "G", "member_user_ids": [b["user"]["id"]]}).json()
    return a, b, c, g["id"]


def _eq(payer, people, total=9000, **extra):
    return {"description": "Dinner", "total": {"amount_minor": total, "currency": "INR"}, "expense_date": "2026-11-05",
            "payers": [{"user_id": payer["user"]["id"], "paid_amount_minor": total}],
            "split": {"type": "equal", "entries": [{"user_id": p["user"]["id"]} for p in people]}, **extra}


def test_group_expense_endpoints(call):
    a, b, c, gid = _people(call)
    ta, tb, tc = _bearer(a), _bearer(b), _bearer(c)
    key = {"Idempotency-Key": "0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1a0301"}
    e = call("POST", f"/groups/{gid}/expenses", 201, token=ta, headers=key, json_body=_eq(a, [a, b])).json()
    call("POST", f"/groups/{gid}/expenses", 201, token=ta, headers=key, json_body=_eq(a, [a, b]))  # replay
    call("POST", f"/groups/{gid}/expenses", 201, token=ta, json_body={
        **_eq(a, [a, b], 10000), "split": {"type": "exact", "entries": [
            {"user_id": a["user"]["id"], "value": 4000}, {"user_id": b["user"]["id"], "value": 6000}]}})
    call("POST", f"/groups/{gid}/expenses", 422, token=ta, json_body={
        **_eq(a, [a, b], 10000), "split": {"type": "exact", "entries": [
            {"user_id": a["user"]["id"], "value": 1}, {"user_id": b["user"]["id"], "value": 6000}]}})
    call("POST", f"/groups/{gid}/expenses", 422, token=ta, json_body={"description": ""})
    call("POST", f"/groups/{gid}/expenses", 403, token=tc, json_body=_eq(c, [c]))
    call("POST", f"/groups/{gid}/expenses", 401, json_body=_eq(a, [a, b]))
    call("GET", f"/groups/{gid}/expenses", 200, token=tb)
    call("GET", f"/groups/{gid}/expenses", 200, token=tb, params={"limit": 1, "include_deleted": "true"})
    call("GET", f"/groups/{gid}/expenses", 403, token=tc)
    call("GET", f"/groups/{gid}/expenses", 401)
    return e


def test_expense_endpoints(call):
    a, b, c, gid = _people(call)
    ta, tb, tc = _bearer(a), _bearer(b), _bearer(c)
    # non-group expense A and C (friends via explicit add)
    call("POST", "/friends", 201, token=ta, json_body={"email": "meera@example.com"})
    ng = call("POST", "/expenses", 201, token=ta, json_body={**_eq(a, [a, c]), "group_id": None}).json()
    ge = call("POST", "/expenses", 201, token=ta, json_body={**_eq(a, [a, b]), "group_id": gid}).json()
    call("POST", "/expenses", 422, token=ta, json_body={**_eq(a, [a, c]), "payers": []})
    call("POST", "/expenses", 401, json_body=_eq(a, [a, c]))
    call("GET", "/expenses", 200, token=ta)
    call("GET", "/expenses", 200, token=ta, params={"non_group": "true", "limit": 1})
    call("GET", "/expenses", 200, token=ta, params={"friend_user_id": c["user"]["id"]})
    call("GET", "/expenses", 401)
    for who in (ng, ge):
        call("GET", f"/expenses/{who['id']}", 200, token=ta)
    call("GET", f"/expenses/{ge['id']}", 403, token=tc)
    call("GET", "/expenses/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff", 404, token=ta)
    call("GET", f"/expenses/{ge['id']}", 401)
    p = call("PATCH", f"/expenses/{ge['id']}", 200, token=tb,
             json_body={"version": ge["version"], "description": "Lunch", "total": {"amount_minor": 12000, "currency": "INR"}}).json()
    call("PATCH", f"/expenses/{ge['id']}", 409, token=ta, json_body={"version": ge["version"], "description": "Stale"})
    call("PATCH", f"/expenses/{ge['id']}", 403, token=tc, json_body={"version": p["version"], "description": "No"})
    call("PATCH", f"/expenses/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff", 404, token=ta,
         json_body={"version": 1, "description": "No"})
    call("PATCH", f"/expenses/{ge['id']}", 422, token=ta, json_body={"description": "no version"})
    call("POST", f"/expenses/{ge['id']}/restore", 409, token=ta)  # NOT_DELETED
    d = call("DELETE", f"/expenses/{ge['id']}", 200, token=ta).json()
    assert d["deleted_at"] is not None
    call("DELETE", f"/expenses/{ge['id']}", 409, token=ta)  # already deleted
    call("DELETE", f"/expenses/{ng['id']}", 403, token=tb)
    call("DELETE", "/expenses/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff", 404, token=ta)
    call("POST", f"/expenses/{ge['id']}/restore", 200, token=ta)


def test_comment_endpoints(call):
    a, b, c, gid = _people(call)
    ta, tb, tc = _bearer(a), _bearer(b), _bearer(c)
    e = call("POST", f"/groups/{gid}/expenses", 201, token=ta, json_body=_eq(a, [a, b])).json()
    path = f"/expenses/{e['id']}/comments"
    call("POST", path, 201, token=tb, json_body={"body": "paid my share"})
    call("POST", path, 201, token=ta, json_body={"body": "thanks"})
    call("POST", path, 422, token=ta, json_body={"body": ""})
    call("POST", path, 403, token=tc, json_body={"body": "hi"})
    call("POST", path, 401, json_body={"body": "hi"})
    first = call("GET", path, 200, token=ta, params={"limit": 1}).json()
    call("GET", path, 200, token=ta, params={"limit": 1, "cursor": first["next_cursor"]})
    call("GET", path, 403, token=tc)
    call("GET", path, 401)
    call("DELETE", f"/expenses/{e['id']}", 200, token=ta)
    call("POST", path, 409, token=ta, json_body={"body": "too late"})  # ALREADY_DELETED


def test_timeline_endpoint(call):
    a, b, c, gid = _people(call)
    ta, tc = _bearer(a), _bearer(c)
    for i in range(3):
        call("POST", f"/groups/{gid}/expenses", 201, token=ta, json_body=_eq(a, [a, b], 3000 + i))
    first = call("GET", f"/groups/{gid}/timeline", 200, token=ta, params={"limit": 2}).json()
    assert first["next_cursor"]
    call("GET", f"/groups/{gid}/timeline", 200, token=ta, params={"limit": 2, "cursor": first["next_cursor"]})
    call("GET", f"/groups/{gid}/timeline", 200, token=ta, params={"include_deleted": "true"})
    call("GET", f"/groups/{gid}/timeline", 401)
    call("GET", f"/groups/{gid}/timeline", 403, token=tc)
    call("GET", "/groups/0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1affff/timeline", 404, token=ta)
    call("GET", f"/groups/{gid}/timeline", 422, token=ta, params={"cursor": "garbage"})


# Must stay last: it needs the COVERED set filled by every contract test above it.
def test_every_in_scope_operation_was_exercised_and_unshipped_ones_are_still_absent():
    """Needs the calls made by the tests above it (module-level COVERED set); skipped if none ran (for example with -k). Fails if an in-scope operation has no contract call, or if an
    operation listed as not implemented gained a route without gaining a contract test."""
    if not COVERED:
        pytest.skip("no contract calls ran in this session")
    spec_ops = {(m, p) for p, item in RAW.items() for m in item if m in
                ("get", "post", "put", "patch", "delete")}
    assert IN_SCOPE <= spec_ops and NOT_YET_IMPLEMENTED <= spec_ops
    missing = IN_SCOPE - COVERED
    if os.environ.get("PYTEST_XDIST_WORKER") is None:
        assert not missing, f"no contract call for {sorted(missing)}"
    shipped_ops = shipped_operations(app)
    in_scope_n = {(m, _norm(p)) for m, p in IN_SCOPE}
    not_yet_n = {(m, _norm(p)) for m, p in NOT_YET_IMPLEMENTED}
    shipped = not_yet_n & shipped_ops
    assert not shipped, f"now implemented, add contract calls and move out of NOT_YET_IMPLEMENTED: {sorted(shipped)}"
    unlisted = shipped_ops - in_scope_n - not_yet_n
    assert not unlisted, f"route has no contract test and is in neither set: {sorted(unlisted)}"
    assert shipped_ops >= in_scope_n, f"in scope but not served: {sorted(in_scope_n - shipped_ops)}"
