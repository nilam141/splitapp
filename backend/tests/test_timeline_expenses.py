"""S3-Q-5: GET /groups/{id}/timeline, expense side of business_rules vector 50. Fails before S3-B-6.

Settlement items (S5) are out of scope here: with no settlements the timeline holds `kind: expense` items only.
Setup needs S3-B-3 (create) and S3-B-4 (DELETE /expenses/{id}); missing pieces show up as a setup assertion naming the
status. created_at is set directly in the database so ties are exact.
"""
import uuid
from datetime import datetime, timezone

import pytest

from tests.expense_helpers import create_group_expense, equal_body, h, make_group, set_created_at, user
from tests.test_openapi_contract import Caller


def ts(hh, mm=0):
    return datetime(2026, 11, 5, hh, mm, tzinfo=timezone.utc)


@pytest.fixture()
def call(client):
    return Caller(client)


@pytest.fixture()
def world(client, db_session):
    """Group G = {A, B}; outsider C. Expense-side fixture of vector 50 plus two identical-created_at expenses.

      E2  2026-11-06 created 09:00
      E3  2026-11-05 created 12:00   (the slot S1 takes in vector 50; same date as E1, later created_at)
      E1  2026-11-05 created 10:00
      E4  2026-11-04 created 11:00   (the slot S2 takes)
      E5, E6  2026-11-03 both created 08:00 exactly -> ordered by id desc
    """
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b])
    spec = {"E1": ("2026-11-05", ts(10)), "E2": ("2026-11-06", ts(9)), "E3": ("2026-11-05", ts(12)),
            "E4": ("2026-11-04", ts(11)), "E5": ("2026-11-03", ts(8)), "E6": ("2026-11-03", ts(8))}
    ids = {}
    for name, (date, created) in spec.items():
        e = create_group_expense(client, a, gid, equal_body(a, [a, b], description=name, date=date))
        set_created_at(db_session, e["id"], created)
        ids[name] = e["id"]
    tie = sorted([ids["E5"], ids["E6"]], reverse=True)  # same date and created_at: id desc
    order = [ids["E2"], ids["E3"], ids["E1"], ids["E4"]] + tie
    return {"a": a, "b": b, "c": c, "gid": gid, "ids": ids, "order": order}


@pytest.fixture()
def plain(client):
    """Group {A, B} with no expenses, outsider C: error-path tests need no S3-B-3/B-4 setup."""
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    return {"a": a, "b": b, "c": c, "gid": make_group(client, a, [b])}


def get(client, who, gid, **params):
    return client.get(f"/groups/{gid}/timeline", params=params, headers=h(who))


def page_ids(body):
    return [i["expense"]["id"] for i in body["items"]]


def walk(client, who, gid, limit, **params):
    """Follow next_cursor to the end; returns the list of pages (each a response body)."""
    pages, cursor = [], None
    for _ in range(50):
        q = dict(params, limit=limit, **({"cursor": cursor} if cursor else {}))
        r = get(client, who, gid, **q)
        assert r.status_code == 200, r.text
        pages.append(r.json())
        cursor = r.json()["next_cursor"]
        if cursor is None:
            return pages
    raise AssertionError("cursor never ended")


# ---- shape and order ---------------------------------------------------------------------------------------------

def test_items_are_expenses_with_date_and_full_expense_object(client, world):
    w = world
    r = get(client, w["a"], w["gid"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "next_cursor"} and body["next_cursor"] is None
    assert len(body["items"]) == 6
    for item in body["items"]:
        assert item["kind"] == "expense"
        assert set(item) == {"kind", "date", "expense"}
        assert item["date"] == item["expense"]["expense_date"]
        assert item["expense"]["group_id"] == w["gid"] and item["expense"]["deleted_at"] is None


def test_order_is_date_desc_then_created_at_desc_then_id_desc(client, world):
    w = world
    assert page_ids(get(client, w["a"], w["gid"]).json()) == w["order"]
    assert page_ids(get(client, w["b"], w["gid"]).json()) == w["order"]  # another member sees the same order


def test_same_date_orders_by_created_at_and_identical_created_at_by_id(client, world):
    w = world
    got = page_ids(get(client, w["a"], w["gid"]).json())
    ids = w["ids"]
    assert got.index(ids["E3"]) < got.index(ids["E1"])  # same date 2026-11-05, 12:00 before 10:00
    e5, e6 = got.index(ids["E5"]), got.index(ids["E6"])
    assert (e5 < e6) == (ids["E5"] > ids["E6"])  # identical date and created_at: larger id first


# ---- soft delete ---------------------------------------------------------------------------------------------------

def test_deleted_expense_hidden_unless_include_deleted(client, world):
    w = world
    victim = w["ids"]["E3"]
    assert client.delete(f"/expenses/{victim}", headers=h(w["a"])).status_code == 200
    hidden = [x for x in w["order"] if x != victim]
    assert page_ids(get(client, w["a"], w["gid"]).json()) == hidden
    assert page_ids(get(client, w["a"], w["gid"], include_deleted="false").json()) == hidden
    shown = get(client, w["a"], w["gid"], include_deleted="true").json()
    assert page_ids(shown) == w["order"]  # deleted item keeps its place in the order
    flagged = {i["expense"]["id"]: i["expense"]["deleted_at"] for i in shown["items"]}
    assert flagged[victim] is not None and all(v is None for k, v in flagged.items() if k != victim)


def test_restored_expense_comes_back(client, world):
    w = world
    victim = w["ids"]["E1"]
    assert client.delete(f"/expenses/{victim}", headers=h(w["a"])).status_code == 200
    assert client.post(f"/expenses/{victim}/restore", headers=h(w["a"])).status_code == 200
    assert page_ids(get(client, w["a"], w["gid"]).json()) == w["order"]


# ---- paging --------------------------------------------------------------------------------------------------------

def test_limit_2_paging_no_duplicate_no_gap_ends_with_null_cursor(client, world):
    w = world
    pages = walk(client, w["a"], w["gid"], 2)
    assert [len(p["items"]) for p in pages] == [2, 2, 2]
    assert [p["next_cursor"] is None for p in pages] == [False, False, True]
    flat = [i for p in pages for i in page_ids(p)]
    assert flat == w["order"] and len(set(flat)) == len(flat)


def test_paging_with_an_odd_page_size_and_with_exact_fit(client, world):
    w = world
    assert [i for p in walk(client, w["a"], w["gid"], 4) for i in page_ids(p)] == w["order"]
    last = walk(client, w["a"], w["gid"], 6)
    assert len(last) == 1 and last[0]["next_cursor"] is None


def test_paging_splits_inside_a_tie_without_loss(client, world):
    """limit=1 puts a page boundary between E5 and E6, which share date and created_at (only id differs)."""
    w = world
    flat = [i for p in walk(client, w["a"], w["gid"], 1) for i in page_ids(p)]
    assert flat == w["order"]


def test_paging_with_include_deleted_is_consistent(client, world):
    w = world
    assert client.delete(f"/expenses/{w['ids']['E2']}", headers=h(w["a"])).status_code == 200
    flat = [i for p in walk(client, w["a"], w["gid"], 2, include_deleted="true") for i in page_ids(p)]
    assert flat == w["order"]


@pytest.mark.parametrize("date,created,where", [
    ("2026-11-07", ts(20), "before"),   # newer than everything: sorts before page 1's items
    ("2026-11-02", ts(7), "after"),     # older than everything: sorts after the cursor
])
def test_expense_created_between_pages_does_not_duplicate_or_skip(client, db_session, world, date, created, where):
    w = world
    page1 = get(client, w["a"], w["gid"], limit=2).json()
    assert page_ids(page1) == w["order"][:2]
    new = create_group_expense(client, w["a"], w["gid"],
                               equal_body(w["a"], [w["a"], w["b"]], description="late", date=date))
    set_created_at(db_session, new["id"], created)

    rest, cursor = [], page1["next_cursor"]
    while cursor:
        r = get(client, w["a"], w["gid"], limit=2, cursor=cursor)
        assert r.status_code == 200, r.text
        rest += page_ids(r.json())
        cursor = r.json()["next_cursor"]
    seen = page_ids(page1) + rest
    assert len(seen) == len(set(seen))                           # no duplicate
    assert [x for x in seen if x != new["id"]] == w["order"]     # every existing item exactly once, same order
    if where == "before":
        assert new["id"] not in seen   # sorts before page 1; the cursor is already past it
    else:
        assert seen[-1] == new["id"]   # sorts after every existing item: appears once, at the end


def test_deleting_between_pages_does_not_skip_or_duplicate(client, world):
    w = world
    page1 = get(client, w["a"], w["gid"], limit=2).json()
    assert client.delete(f"/expenses/{w['ids']['E1']}", headers=h(w["a"])).status_code == 200  # ahead of the cursor
    rest, cursor = [], page1["next_cursor"]
    while cursor:
        r = get(client, w["a"], w["gid"], limit=2, cursor=cursor).json()
        rest += page_ids(r)
        cursor = r["next_cursor"]
    assert page_ids(page1) + rest == [x for x in w["order"] if x != w["ids"]["E1"]]


# ---- auth and errors -----------------------------------------------------------------------------------------------

def test_non_member_is_403_forbidden(client, plain):
    w = plain
    r = get(client, w["c"], w["gid"])
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    assert "items" not in r.json()


def test_member_who_left_is_403(client, plain):
    w = plain
    assert client.delete(f"/groups/{w['gid']}/members/me", headers=h(w["b"])).status_code == 204
    assert get(client, w["b"], w["gid"]).status_code == 403


def test_unknown_group_is_404_not_found(client, plain):
    assert get(client, plain["a"], plain["gid"]).status_code == 200  # the route exists (else 404 proves nothing)
    r = get(client, plain["a"], str(uuid.uuid4()))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_no_token_is_401(client, plain):
    assert client.get(f"/groups/{plain['gid']}/timeline").status_code == 401


@pytest.mark.parametrize("cursor", ["garbage", "!!!", "e30", "a" * 400])
def test_bad_cursor_is_422_validation_error(client, plain, cursor):
    r = get(client, plain["a"], plain["gid"], cursor=cursor)
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["fields"][0]["field"] == "cursor"


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_limit_out_of_range_is_422(client, plain, limit):
    r = get(client, plain["a"], plain["gid"], limit=limit)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_limit_100_is_accepted(client, plain):
    assert get(client, plain["a"], plain["gid"], limit=100).status_code == 200


def test_cursor_from_another_group_does_not_leak_items(client, world):
    """A cursor is keyset data only: using group 1's cursor on group 2 must not return group 1's expenses."""
    w = world
    g2 = make_group(client, w["a"], [w["b"]], name="G2")
    mine = create_group_expense(client, w["a"], g2, equal_body(w["a"], [w["a"], w["b"]], description="other"))
    cur = get(client, w["a"], w["gid"], limit=2).json()["next_cursor"]
    r = get(client, w["a"], g2, limit=2, cursor=cur)
    if r.status_code == 200:  # accepted as a plain keyset position is fine; leaking the other group is not
        assert set(page_ids(r.json())).isdisjoint(w["order"]) and set(page_ids(r.json())) <= {mine["id"]}
    else:
        assert r.status_code == 422


def test_empty_group_returns_empty_page(client):
    a = user(client, "Asha")
    gid = make_group(client, a, [])
    r = get(client, a, gid)
    assert r.status_code == 200 and r.json() == {"items": [], "next_cursor": None}


# ---- contract ------------------------------------------------------------------------------------------------------

def test_responses_validate_against_timeline_page_schema(call, world):
    # `world` already registers outsider C (not in the group); `plain` would register the same emails again.
    w = world
    plain = {"c": w["c"]}
    tok = w["a"]["access_token"]
    first = call("GET", f"/groups/{w['gid']}/timeline", 200, token=tok, params={"limit": 2}).json()
    call("GET", f"/groups/{w['gid']}/timeline", 200, token=tok, params={"limit": 2, "cursor": first["next_cursor"]})
    call("GET", f"/groups/{w['gid']}/timeline", 200, token=tok, params={"include_deleted": "true"})
    call("GET", f"/groups/{w['gid']}/timeline", 403, token=plain["c"]["access_token"])
    call("GET", f"/groups/{uuid.uuid4()}/timeline", 404, token=tok)
    call("GET", f"/groups/{w['gid']}/timeline", 422, token=tok, params={"cursor": "garbage"})
    call("GET", f"/groups/{w['gid']}/timeline", 401)
