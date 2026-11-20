"""S5-Q-1: settlement rules, business_rules vectors 25, 26, 27, 32, 41 (settlement half), 51 and 66, settle-all,
SAME_PARTY, currency isolation, who-can-record, authorization. Written before S5-B-2: every test fails at the first
POST /settlements (404, no such route), which the setup assertion reports as "needs S5-B-2" (vector 51: the
non-group-settlement soft delete is S5-B-4, so it fails on the settlement row still being live after DELETE /friends).
Responses are validated against docs/openapi.yaml through the shared Caller.
"""
import uuid

import pytest

from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user
from tests.settlement_helpers import befriend, pay, sbody, settlement_deleted_at
from tests.test_balances_api import exact_body, group_balances, member_lines, nongroup_owes, owes, set_simplify
from tests.test_openapi_contract import Caller

CODE = "EXPENSE_HAS_DEPARTED_MEMBER"


@pytest.fixture()
def call(client):
    return Caller(client)


@pytest.fixture()
def w(client):
    """Group G = {A, B, C}; outsider Z. Two-person scenarios use A and B (C stays at 0)."""
    a, b, c, z = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Zed"))
    return {"a": a, "b": b, "c": c, "z": z, "gid": make_group(client, a, [b, c])}


def friend_lines(client, who, other):
    r = client.get(f"/friends/{uid(other)}", headers=h(who))
    assert r.status_code == 200, r.text
    return {x["currency"]: x["amount_minor"] for x in r.json()["balances"] if x["amount_minor"] != 0}


def group_nets(client, who, gid):
    return member_lines(group_balances(client, who, gid))


# ---- vectors 25, 26, 27 (group and non-group scope) ---------------------------------------------------------------

CASES = [  # id, B owes A before, B pays, expected A-view balance after (positive = B owes A)
    pytest.param(5000, 2000, 3000, id="vector-25-partial"),
    pytest.param(3000, 3000, 0, id="vector-26-full"),
    pytest.param(3000, 5000, -2000, id="vector-27-overpayment"),
]


@pytest.mark.parametrize("owed,paid,after", CASES)
def test_group_scope_vectors_25_26_27(client, w, owed, paid, after):
    a, b, gid = w["a"], w["b"], w["gid"]
    owes(client, a, gid, b, owed)
    s = pay(client, b, b, a, paid, group_id=gid)
    assert s["amount"] == {"amount_minor": paid, "currency": "INR"} and s["group_id"] == gid
    assert s["from_user_id"] == uid(b) and s["to_user_id"] == uid(a) and s["version"] == 1 and s["deleted_at"] is None
    nets = group_nets(client, a, gid)
    assert nets[uid(a)].get("INR", 0) == after and nets[uid(b)].get("INR", 0) == -after
    assert nets[uid(w["c"])].get("INR", 0) == 0
    transfers = group_balances(client, a, gid)["transfers"]
    if after == 0:
        assert transfers == []
    else:  # owed direction follows the sign: after > 0 B pays A; after < 0 A pays B (overpayment flips it)
        frm, to = (uid(b), uid(a)) if after > 0 else (uid(a), uid(b))
        assert [(t["from_user_id"], t["to_user_id"], t["amount_minor"]) for t in transfers] == [(frm, to, abs(after))]


@pytest.mark.parametrize("owed,paid,after", CASES)
def test_non_group_scope_vectors_25_26_27(client, w, owed, paid, after):
    a, b = w["a"], w["b"]
    befriend(client, a, b)
    nongroup_owes(client, a, b, owed)
    s = pay(client, b, b, a, paid)
    assert s["group_id"] is None
    got = friend_lines(client, a, b)
    assert got.get("INR", 0) == after
    assert friend_lines(client, b, a).get("INR", 0) == -after


def test_partial_then_full_flow_05_style(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    owes(client, a, gid, b, 5000)
    pay(client, b, b, a, 2000, group_id=gid)
    assert group_nets(client, a, gid)[uid(b)]["INR"] == -3000
    pay(client, b, b, a, 3000, group_id=gid)
    nets = group_nets(client, a, gid)
    assert all(v.get("INR", 0) == 0 for v in nets.values())
    assert group_balances(client, a, gid)["transfers"] == []


# ---- vector 32 ---------------------------------------------------------------------------------------------------

def test_vector_32_edit_after_settle(client, w):
    a, b, c, gid = w["a"], w["b"], w["c"], w["gid"]
    e = create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=9000))
    pay(client, c, c, a, 3000, group_id=gid)
    assert group_nets(client, a, gid)[uid(c)].get("INR", 0) == 0
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 12000, "currency": "INR"}},
                     headers=h(a))
    assert r.status_code == 200, r.text
    nets = group_nets(client, a, gid)
    assert nets[uid(c)]["INR"] == -1000          # C owes A 1000 again (4000 share - 3000 paid)
    assert nets[uid(b)]["INR"] == -4000
    assert nets[uid(a)]["INR"] == 5000
    assert sum(v.get("INR", 0) for v in nets.values()) == 0


# ---- rules: SAME_PARTY, amounts, currency, membership, who can record ------------------------------------------

def test_same_party_is_422(client, w, call):
    a = w["a"]
    r = call("POST", "/settlements", 422, token=a["access_token"], json_body=sbody(a, a, 1000, group_id=w["gid"]))
    assert r.json()["code"] == "SAME_PARTY"
    r = call("POST", "/settlements", 422, token=a["access_token"], json_body=sbody(a, a, 1000))
    assert r.json()["code"] == "SAME_PARTY"


@pytest.mark.parametrize("amount,code", [(0, "AMOUNT_OUT_OF_RANGE"), (-5, "AMOUNT_OUT_OF_RANGE"),
                                         (10_000_000_000, "AMOUNT_OUT_OF_RANGE")])
def test_amount_bounds_are_422(client, w, amount, code):
    a, b = w["a"], w["b"]
    r = client.post("/settlements", json=sbody(b, a, amount, group_id=w["gid"]), headers=h(b))
    assert r.status_code == 422, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["code"] in (code, "VALIDATION_ERROR")


def test_maximum_amount_is_accepted(client, w):
    pay(client, w["b"], w["b"], w["a"], 9_999_999_999, group_id=w["gid"])


def test_unknown_currency_is_422(client, w):
    r = client.post("/settlements", json=sbody(w["b"], w["a"], 100, currency="ZZZ", group_id=w["gid"]),
                    headers=h(w["b"]))
    assert r.status_code == 422, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["code"] == "CURRENCY_UNKNOWN"


def test_group_settlement_with_a_non_member_party_is_422(client, w):
    a, z = w["a"], w["z"]
    r = client.post("/settlements", json=sbody(z, a, 100, group_id=w["gid"]), headers=h(a))
    assert r.status_code == 422, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["code"] == "PARTICIPANT_NOT_MEMBER"
    r = client.post("/settlements", json=sbody(a, z, 100, group_id=w["gid"]), headers=h(a))
    assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"


def test_group_settlement_unknown_group_is_404(client, w):
    pay(client, w["b"], w["b"], w["a"], 100, group_id=w["gid"])      # proves the route exists (else 404 is vacuous)
    r = client.post("/settlements", json=sbody(w["b"], w["a"], 100, group_id=str(uuid.uuid4())), headers=h(w["a"]))
    assert r.status_code == 404, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"


def test_any_group_member_may_record_a_group_settlement(client, w):
    a, b, c, gid = w["a"], w["b"], w["c"], w["gid"]
    owes(client, a, gid, b, 1000)
    s = pay(client, c, b, a, 1000, group_id=gid)          # C is neither payer nor receiver but is a member
    assert s["created_by"] == uid(c)
    assert group_nets(client, a, gid)[uid(b)].get("INR", 0) == 0


def test_group_settlement_by_a_non_member_is_403(client, w):
    z = w["z"]
    r = client.post("/settlements", json=sbody(w["b"], w["a"], 100, group_id=w["gid"]), headers=h(z))
    assert r.status_code == 403, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["code"] == "FORBIDDEN"


def test_non_group_settlement_by_a_third_party_is_403(client, w):
    a, b, c = w["a"], w["b"], w["c"]
    befriend(client, a, b)
    r = client.post("/settlements", json=sbody(b, a, 100), headers=h(c))
    assert r.status_code == 403, f"POST /settlements -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["code"] == "FORBIDDEN"
    assert pay(client, a, b, a, 100)["created_by"] == uid(a)       # the receiver may record it
    assert pay(client, b, b, a, 100)["created_by"] == uid(b)       # and so may the payer


def test_currency_isolation_usd_payment_leaves_the_inr_debt(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    owes(client, a, gid, b, 5000, "INR")
    pay(client, b, b, a, 100, "USD", group_id=gid)
    nets = group_nets(client, a, gid)
    assert nets[uid(b)] == {"INR": -5000, "USD": 100}       # INR debt intact, a new USD balance appears
    assert nets[uid(a)] == {"INR": 5000, "USD": -100}


# ---- edit, delete, restore, versions -------------------------------------------------------------------------------

def test_patch_delete_restore_recompute_balances(client, w, call):
    a, b, gid = w["a"], w["b"], w["gid"]
    tok = a["access_token"]
    owes(client, a, gid, b, 5000)
    s = pay(client, b, b, a, 2000, group_id=gid)
    got = call("PATCH", f"/settlements/{s['id']}", 200, token=tok,
               json_body={"version": 1, "amount": {"amount_minor": 2500, "currency": "INR"}, "note": "cash"}).json()
    assert got["version"] == 2 and got["amount"]["amount_minor"] == 2500 and got["note"] == "cash"
    assert group_nets(client, a, gid)[uid(b)]["INR"] == -2500
    d = call("DELETE", f"/settlements/{s['id']}", 200, token=tok).json()
    assert d["deleted_at"] is not None
    assert group_nets(client, a, gid)[uid(b)]["INR"] == -5000
    r = call("POST", f"/settlements/{s['id']}/restore", 200, token=tok).json()
    assert r["deleted_at"] is None
    assert group_nets(client, a, gid)[uid(b)]["INR"] == -2500


def test_stale_version_is_409(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    s = pay(client, b, b, a, 100, group_id=gid)
    ok = client.patch(f"/settlements/{s['id']}", json={"version": 1, "note": "x"}, headers=h(a))
    assert ok.status_code == 200, ok.text
    r = client.patch(f"/settlements/{s['id']}", json={"version": 1, "note": "y"}, headers=h(a))
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"


def test_delete_twice_and_restore_live_are_409(client, w, call):
    a, b, gid = w["a"], w["b"], w["gid"]
    tok = a["access_token"]
    s = pay(client, b, b, a, 100, group_id=gid)
    assert call("POST", f"/settlements/{s['id']}/restore", 409, token=tok).json()["code"] == "NOT_DELETED"
    call("DELETE", f"/settlements/{s['id']}", 200, token=tok)
    assert call("DELETE", f"/settlements/{s['id']}", 409, token=tok).json()["code"] == "ALREADY_DELETED"


def test_unknown_settlement_is_404(client, w, call):
    pay(client, w["b"], w["b"], w["a"], 100, group_id=w["gid"])      # proves the route exists (else 404 is vacuous)
    tok, ghost = w["a"]["access_token"], uuid.uuid4()
    call("GET", f"/settlements/{ghost}", 404, token=tok)
    call("PATCH", f"/settlements/{ghost}", 404, token=tok, json_body={"version": 1, "note": "x"})
    call("DELETE", f"/settlements/{ghost}", 404, token=tok)
    call("POST", f"/settlements/{ghost}/restore", 404, token=tok)


def test_idempotency_key_replays_the_same_settlement(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    hdr = {**h(b), "Idempotency-Key": str(uuid.uuid4())}
    body = sbody(b, a, 700, group_id=gid)
    r1 = client.post("/settlements", json=body, headers=hdr)
    r2 = client.post("/settlements", json=body, headers=hdr)
    assert r1.status_code == 201, f"POST /settlements -> {r1.status_code} (needs S5-B-2): {r1.text}"
    assert r2.status_code == 201 and r2.json() == r1.json()
    assert group_nets(client, a, gid)[uid(b)]["INR"] == 700   # recorded once (overpayment: B now owed 700)


# ---- vector 41 (settlement half, OQ-31) ------------------------------------------------------------------------

def test_vector_41_settlement_patch_with_other_currency_is_422_and_changes_nothing(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    s = pay(client, b, b, a, 10000, group_id=gid)
    r = client.patch(f"/settlements/{s['id']}", json={"version": 1, "amount": {"amount_minor": 10000, "currency": "USD"}},
                     headers=h(a))
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR" and body["details"]["fields"][0]["field"] == "amount.currency"
    after = client.get(f"/settlements/{s['id']}", headers=h(a))
    assert after.status_code == 200 and after.json() == s and after.json()["version"] == 1


def test_vector_41_other_currency_with_a_new_amount_is_still_rejected(client, w):
    a, b = w["a"], w["b"]
    s = pay(client, b, b, a, 10000, group_id=w["gid"])
    r = client.patch(f"/settlements/{s['id']}", json={"version": 1, "amount": {"amount_minor": 99, "currency": "USD"}},
                     headers=h(a))
    assert r.status_code == 422 and r.json()["details"]["fields"][0]["field"] == "amount.currency"
    assert client.get(f"/settlements/{s['id']}", headers=h(a)).json() == s


def test_vector_41_same_currency_with_a_new_amount_succeeds(client, w):
    a, b = w["a"], w["b"]
    s = pay(client, b, b, a, 10000, group_id=w["gid"])
    r = client.patch(f"/settlements/{s['id']}", json={"version": 1, "amount": {"amount_minor": 12000, "currency": "INR"}},
                     headers=h(a))
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == {"amount_minor": 12000, "currency": "INR"} and r.json()["version"] == 2


# ---- settle-all ----------------------------------------------------------------------------------------------------

@pytest.fixture()
def multi(client, w):
    """A and B: group G (INR: B owes A 3000; USD: A owes B 500) and the non-group space (INR: B owes A 1000)."""
    a, b, gid = w["a"], w["b"], w["gid"]
    set_simplify(client, a, gid, False)
    befriend(client, a, b)
    owes(client, a, gid, b, 3000, "INR")
    owes(client, b, gid, a, 500, "USD")
    nongroup_owes(client, a, b, 1000, "INR")
    return w


def edge_key(s):
    return (s["group_id"], s["amount"]["currency"], s["from_user_id"], s["to_user_id"], s["amount"]["amount_minor"])


def test_settle_all_creates_one_settlement_per_scope_and_currency_with_a_shared_batch(client, multi, call):
    a, b, gid = multi["a"], multi["b"], multi["gid"]
    r = call("POST", "/settlements/settle-all", 201, token=a["access_token"], json_body={"friend_user_id": uid(b)})
    body = r.json()
    items = body["items"]
    assert len(items) == 3
    assert {s["batch_id"] for s in items} == {body["batch_id"]}
    assert {edge_key(s) for s in items} == {
        (gid, "INR", uid(b), uid(a), 3000), (gid, "USD", uid(a), uid(b), 500), (None, "INR", uid(b), uid(a), 1000)}
    assert all(s["created_by"] == uid(a) and s["version"] == 1 and s["deleted_at"] is None for s in items)
    assert group_nets(client, a, gid)[uid(b)].get("INR", 0) == 0 and group_nets(client, a, gid)[uid(b)].get("USD", 0) == 0
    assert friend_lines(client, a, b) == {}
    assert group_balances(client, a, gid)["transfers"] == []
    again = call("POST", "/settlements/settle-all", 201, token=a["access_token"], json_body={"friend_user_id": uid(b)})
    assert again.json()["items"] == []                      # already settled: empty list


def test_settle_all_can_be_limited_to_one_currency(client, multi):
    a, b, gid = multi["a"], multi["b"], multi["gid"]
    r = client.post("/settlements/settle-all", json={"friend_user_id": uid(b), "currency": "INR"}, headers=h(a))
    assert r.status_code == 201, f"POST /settlements/settle-all -> {r.status_code} (needs S5-B-2): {r.text}"
    assert {edge_key(s) for s in r.json()["items"]} == {
        (gid, "INR", uid(b), uid(a), 3000), (None, "INR", uid(b), uid(a), 1000)}
    assert group_nets(client, a, gid)[uid(a)] == {"USD": -500}      # the USD edge is untouched


def test_settle_all_with_nothing_owed_returns_an_empty_batch(client, w):
    a, b = w["a"], w["b"]
    befriend(client, a, b)
    r = client.post("/settlements/settle-all", json={"friend_user_id": uid(b)}, headers=h(a))
    assert r.status_code == 201, f"POST /settlements/settle-all -> {r.status_code} (needs S5-B-2): {r.text}"
    assert r.json()["items"] == [] and uuid.UUID(r.json()["batch_id"])


# ---- authorization -------------------------------------------------------------------------------------------------

def test_non_member_cannot_read_or_modify_group_settlements(client, w):
    a, b, z, gid = w["a"], w["b"], w["z"], w["gid"]
    s = pay(client, b, b, a, 1000, group_id=gid)
    got = client.get(f"/settlements/{s['id']}", headers=h(z))
    # openapi declares only 404 for GET /settlements/{id} while GET /expenses/{id} declares 403: ambiguous, see handoff
    assert got.status_code in (403, 404), got.text
    assert "amount" not in got.json()
    assert client.patch(f"/settlements/{s['id']}", json={"version": 1, "note": "x"}, headers=h(z)).status_code == 403
    assert client.delete(f"/settlements/{s['id']}", headers=h(z)).status_code == 403
    assert client.get(f"/settlements/{s['id']}", headers=h(a)).json() == s        # unchanged
    client.delete(f"/settlements/{s['id']}", headers=h(a))
    assert client.post(f"/settlements/{s['id']}/restore", headers=h(z)).status_code == 403


def test_non_party_cannot_touch_a_non_group_settlement(client, w):
    a, b, c = w["a"], w["b"], w["c"]
    befriend(client, a, b)
    s = pay(client, b, b, a, 1000)
    assert client.get(f"/settlements/{s['id']}", headers=h(c)).status_code in (403, 404)
    assert client.patch(f"/settlements/{s['id']}", json={"version": 1, "note": "x"}, headers=h(c)).status_code == 403
    assert client.delete(f"/settlements/{s['id']}", headers=h(c)).status_code == 403


def test_list_shows_only_settlements_involving_the_caller(client, w, call):
    a, b, c, z, gid = w["a"], w["b"], w["c"], w["z"], w["gid"]
    s1 = pay(client, b, b, a, 100, group_id=gid)
    s2 = pay(client, b, b, a, 200, group_id=gid)
    s3 = pay(client, c, c, b, 300, group_id=gid)
    ids = lambda r: [i["id"] for i in r.json()["items"]]
    mine = call("GET", "/settlements", 200, token=a["access_token"])
    assert set(ids(mine)) == {s1["id"], s2["id"]} and mine.json()["next_cursor"] is None
    assert set(ids(call("GET", "/settlements", 200, token=c["access_token"]))) == {s3["id"]}
    assert ids(call("GET", "/settlements", 200, token=z["access_token"])) == []
    page1 = call("GET", "/settlements", 200, token=b["access_token"], params={"limit": 2}).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = call("GET", "/settlements", 200, token=b["access_token"],
                 params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    assert len(page2["items"]) == 1 and page2["next_cursor"] is None
    assert {i["id"] for i in page1["items"] + page2["items"]} == {s1["id"], s2["id"], s3["id"]}
    byfriend = call("GET", "/settlements", 200, token=a["access_token"], params={"friend_user_id": uid(c)})
    assert ids(byfriend) == []
    # filtering by someone else's group: refused (403) or empty, never another member's data
    r = client.get("/settlements", params={"group_id": gid}, headers=h(z))
    assert r.status_code in (403, 404) or (r.status_code == 200 and r.json()["items"] == [])


def test_unauthenticated_calls_are_401(client):
    for method, path in [("get", "/settlements"), ("post", "/settlements"), ("post", "/settlements/settle-all"),
                         ("get", f"/settlements/{uuid.uuid4()}")]:
        assert getattr(client, method)(path).status_code == 401, (method, path)


def test_responses_validate_against_the_openapi_schemas(client, w, call):
    a, b, z, gid = w["a"], w["b"], w["z"], w["gid"]
    ta, tz = a["access_token"], z["access_token"]
    s = call("POST", "/settlements", 201, token=b["access_token"], json_body=sbody(b, a, 500, group_id=gid)).json()
    call("POST", "/settlements", 403, token=tz, json_body=sbody(b, a, 500, group_id=gid))
    call("POST", "/settlements", 422, token=ta, json_body=sbody(a, a, 500, group_id=gid))
    call("GET", f"/settlements/{s['id']}", 200, token=ta)
    call("GET", "/settlements", 200, token=ta)
    call("PATCH", f"/settlements/{s['id']}", 200, token=ta, json_body={"version": 1, "note": "n"})
    call("PATCH", f"/settlements/{s['id']}", 409, token=ta, json_body={"version": 1, "note": "m"})
    call("PATCH", f"/settlements/{s['id']}", 422, token=ta,
         json_body={"version": 2, "amount": {"amount_minor": 5, "currency": "USD"}})
    call("DELETE", f"/settlements/{s['id']}", 200, token=ta)
    call("DELETE", f"/settlements/{s['id']}", 409, token=ta)
    call("POST", f"/settlements/{s['id']}/restore", 200, token=ta)
    call("POST", f"/settlements/{s['id']}/restore", 409, token=ta)
    owes(client, a, gid, b, 3000)
    call("POST", "/settlements/settle-all", 201, token=ta, json_body={"friend_user_id": uid(b), "currency": None})


# ---- vector 51 -----------------------------------------------------------------------------------------------------

def test_vector_51_removing_a_friend_soft_deletes_the_pairs_non_group_settlements(client, db_session):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    befriend(client, a, b)
    befriend(client, a, c)
    befriend(client, c, b)
    e = create_expense(client, a, {**equal_body(a, [a, b], total=6000), "group_id": None})     # B owes A 3000
    s = pay(client, b, b, a, 1000)                                                              # B now owes A 2000
    assert friend_lines(client, a, b) == {"INR": 2000}
    c_exp = create_expense(client, a, {**equal_body(a, [a, c], total=4000), "group_id": None})
    c_set = pay(client, c, c, b, 700)                                                           # C-B, not involving A
    r = client.delete(f"/friends/{uid(b)}", headers=h(a))
    assert r.status_code == 204, r.text
    from tests.expense_helpers import expenses_table
    from sqlalchemy import select
    t = expenses_table()
    db_session.expire_all()
    deleted = lambda eid: db_session.execute(select(t.c.deleted_at).where(t.c.id == uuid.UUID(eid))).scalar_one()
    assert deleted(e["id"]) is not None and deleted(c_exp["id"]) is None
    assert settlement_deleted_at(db_session, s["id"]) is not None, "non-group settlement must be soft-deleted (S5-B-4)"
    assert settlement_deleted_at(db_session, c_set["id"]) is None
    assert client.get(f"/friends/{uid(b)}", headers=h(a)).status_code == 404
    ob = client.get("/balances", headers=h(a))
    assert ob.status_code == 200, ob.text
    assert all(x["amount_minor"] == 0 for f in ob.json()["by_friend"] if f["user_id"] == uid(b) for x in f["balances"])
    assert friend_lines(client, a, c) == {"INR": 2000}                                          # C's expense intact
    assert friend_lines(client, c, b) == {"INR": 700}                                           # C-B settlement intact


def test_vector_51_group_settlements_survive_friend_removal(client, db_session):
    """The pair first shared a group (balanced there), then B left: explicit friends with no shared group."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=6000))
    gs = pay(client, b, b, a, 3000, group_id=gid)
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    befriend(client, a, b)
    ns = pay(client, b, b, a, 400)
    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204
    assert settlement_deleted_at(db_session, gs["id"]) is None
    assert settlement_deleted_at(db_session, ns["id"]) is not None


# ---- vector 66 (S4-Q-4, gated on S5-B-2) -------------------------------------------------------------------------

def is_409(r):
    return r.status_code == 409 and r.json()["code"] == CODE


def test_vector_66_group_settlement_with_a_departed_party_is_409_until_rejoin(client, w):
    a, b, c, gid = w["a"], w["b"], w["c"], w["gid"]
    dead = pay(client, b, b, a, 1000, group_id=gid)                  # an overpayment, deleted while B is a member
    assert client.delete(f"/settlements/{dead['id']}", headers=h(a)).status_code == 200
    owes(client, a, gid, b, 1000)
    live = pay(client, b, b, a, 1000, group_id=gid)                  # B is now at 0 net
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    patch = client.patch(f"/settlements/{live['id']}", json={"version": 1, "note": "x"}, headers=h(a))
    assert is_409(patch), patch.text
    assert is_409(client.delete(f"/settlements/{live['id']}", headers=h(a)))
    assert is_409(client.post(f"/settlements/{dead['id']}/restore", headers=h(a)))
    assert client.get(f"/settlements/{live['id']}", headers=h(a)).json() == live
    assert client.get(f"/settlements/{dead['id']}", headers=h(a)).json()["deleted_at"] is not None
    # check order: ALREADY_DELETED / NOT_DELETED come before the departed check
    assert client.post(f"/settlements/{live['id']}/restore", headers=h(a)).json()["code"] == "NOT_DELETED"
    assert client.delete(f"/settlements/{dead['id']}", headers=h(a)).json()["code"] == "ALREADY_DELETED"
    # the receiver departing is the same: covered by the payer case above; now B rejoins and all three work
    r = client.post(f"/groups/{gid}/members", json={"user_ids": [uid(b)]}, headers=h(a))
    assert r.status_code == 200, r.text
    assert client.patch(f"/settlements/{live['id']}", json={"version": 1, "note": "x"}, headers=h(a)).status_code == 200
    assert client.delete(f"/settlements/{live['id']}", headers=h(a)).status_code == 200
    assert client.post(f"/settlements/{live['id']}/restore", headers=h(a)).status_code == 200
    assert client.post(f"/settlements/{dead['id']}/restore", headers=h(a)).status_code == 200


def test_vector_66_departed_receiver_blocks_too(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    owes(client, b, gid, a, 1000)                                    # A owes B 1000
    live = pay(client, a, a, b, 1000, group_id=gid)                  # receiver is B
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    assert is_409(client.patch(f"/settlements/{live['id']}", json={"version": 1, "note": "x"}, headers=h(a)))
    assert is_409(client.delete(f"/settlements/{live['id']}", headers=h(a)))


def test_vector_66_non_group_restore_needs_friendship(client):
    a, b = user(client, "Dana"), user(client, "Eli")          # share no group, so DELETE /friends is not 409
    befriend(client, a, b)
    s = pay(client, b, b, a, 1000)
    assert client.delete(f"/settlements/{s['id']}", headers=h(a)).status_code == 200
    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204
    r = client.post(f"/settlements/{s['id']}/restore", headers=h(a))
    assert is_409(r), r.text
    befriend(client, a, b)                                           # POST /friends again
    assert client.post(f"/settlements/{s['id']}/restore", headers=h(a)).status_code == 200
