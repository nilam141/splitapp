"""S3-B-3: POST/GET expenses (group and non-group), FLOW-03 a-h, validation errors, idempotency, listing, auth."""
import uuid

import pytest
from sqlalchemy import func, select

from app.models import Expense
from tests.expense_helpers import (create_expense, create_group_expense, equal_body, h, make_group, set_created_at,
                                   uid, user)
from tests.test_openapi_contract import Caller


@pytest.fixture()
def g(client):
    """Group G = A (creator, sort 0), B, C; outsider D."""
    a, b, c, d = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev"))
    return {"a": a, "b": b, "c": c, "d": d, "gid": make_group(client, a, [b, c])}


def body(payers, split_type, entries, total, description="Item", currency="INR", date="2026-11-05", **extra):
    return {"description": description, "total": {"amount_minor": total, "currency": currency}, "expense_date": date,
            "payers": [{"user_id": uid(u), "paid_amount_minor": amt} for u, amt in payers],
            "split": {"type": split_type, "entries": [({"user_id": uid(u)} if v is None else
                                                        {"user_id": uid(u), "value": v}) for u, v in entries]},
            **extra}


def owed(exp):
    return [s["owed_amount_minor"] for s in exp["splits"]]


def count_expenses(db):
    return db.scalar(select(func.count()).select_from(Expense))


# ---- FLOW-03 a-h ---------------------------------------------------------------------------------------------------

def test_flow_03a_equal(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 10000)], "equal", [(a, None), (b, None), (c, None)], 10000,
                                                        "Groceries"))
    assert owed(e) == [3334, 3333, 3333] and [s["user_id"] for s in e["splits"]] == [uid(a), uid(b), uid(c)]
    assert e["my_net"] == {"amount_minor": 6666, "currency": "INR"}
    assert e["group_id"] == g["gid"] and e["split_type"] == "equal" and e["version"] == 1
    assert e["payers"] == [{"user_id": uid(a), "paid_amount_minor": 10000}]
    assert all(s["input_value"] is None for s in e["splits"])
    assert (e["category_id"], e["comment_count"], e["deleted_at"], e["receipt_url"], e["recurring_rule_id"]) == \
           (1, 0, None, None, None)
    assert e["created_by"] == uid(a) and e["updated_by"] is None and e["notes"] is None
    # B's view of the same expense: my_net = -3333
    assert client.get(f"/expenses/{e['id']}", headers=h(b)).json()["my_net"]["amount_minor"] == -3333


def test_flow_03b_exact(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 245000)], "exact", [(a, 100000), (b, 80000), (c, 65000)],
                                                        245000))
    assert owed(e) == [100000, 80000, 65000] and [s["input_value"] for s in e["splits"]] == [100000, 80000, 65000]
    assert e["my_net"]["amount_minor"] == 145000


def test_flow_03c_percent(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 1000)], "percent", [(a, 3333), (b, 3333), (c, 3334)], 1000))
    assert owed(e) == [333, 333, 334] and [s["input_value"] for s in e["splits"]] == [3333, 3333, 3334]


def test_flow_03d_shares(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 60000)], "shares", [(a, 1), (b, 2), (c, 3)], 60000))
    assert owed(e) == [10000, 20000, 30000]


def test_flow_03e_adjustment(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 10000)], "adjustment", [(a, 1000), (b, 0), (c, 0)], 10000))
    assert owed(e) == [4000, 3000, 3000] and [s["input_value"] for s in e["splits"]] == [1000, 0, 0]


def test_flow_03f_two_person_shortcut_non_group(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    e = create_expense(client, a, {**body([(a, 30000)], "exact", [(a, 0), (b, 30000)], 30000, "Cab"), "group_id": None})
    assert e["group_id"] is None and owed(e) == [0, 30000] and e["my_net"]["amount_minor"] == 30000
    assert len(e["splits"]) == 2  # the zero-owing participant keeps a row


def test_flow_03g_multiple_payers(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 60000), (b, 30000)], "equal", [(a, None), (b, None),
                                                                                           (c, None)], 90000, "Dinner"))
    assert owed(e) == [30000, 30000, 30000]
    assert sorted(p["paid_amount_minor"] for p in e["payers"]) == [30000, 60000]
    nets = {m: client.get(f"/expenses/{e['id']}", headers=h(u)).json()["my_net"]["amount_minor"]
            for m, u in (("a", a), ("b", b), ("c", c))}
    assert nets == {"a": 30000, "b": 0, "c": -30000}  # vector 17


def test_flow_03g_error_payers_under(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    r = client.post(f"/groups/{g['gid']}/expenses", headers=h(a),
                    json=body([(a, 60000), (b, 20000)], "equal", [(a, None), (b, None), (c, None)], 90000))
    assert r.status_code == 422 and r.json()["code"] == "PAYER_SUM_MISMATCH"
    assert r.json()["details"] == {"expected": 90000, "actual": 80000, "difference": -10000}


def test_flow_03h_other_currency(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 4500)], "equal", [(a, None), (b, None), (c, None)], 4500,
                                                        "Museum", currency="USD"))
    assert e["total"] == {"amount_minor": 4500, "currency": "USD"} and owed(e) == [1500, 1500, 1500]
    assert e["my_net"]["currency"] == "USD"
    lower = create_group_expense(client, a, g["gid"], body([(a, 100)], "equal", [(a, None)], 100, currency="usd"))
    assert lower["total"]["currency"] == "USD"


# ---- group path rules ----------------------------------------------------------------------------------------------

def test_body_group_id_is_ignored_on_the_group_path(client, g):
    a, b = g["a"], g["b"]
    other = make_group(client, a, [b], name="Other")
    e = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b]), "group_id": other})
    assert e["group_id"] == g["gid"]
    e2 = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b]), "group_id": str(uuid.uuid4())})
    assert e2["group_id"] == g["gid"]


def test_post_expenses_with_body_group_id_is_a_group_expense_and_needs_membership(client, g):
    a, b, d = g["a"], g["b"], g["d"]
    e = create_expense(client, a, {**equal_body(a, [a, b]), "group_id": g["gid"]})
    assert e["group_id"] == g["gid"]
    r = client.post("/expenses", json={**equal_body(d, [d]), "group_id": g["gid"]}, headers=h(d))
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    r = client.post("/expenses", json={**equal_body(a, [a]), "group_id": str(uuid.uuid4())}, headers=h(a))
    assert r.status_code == 404


def test_non_member_cannot_post_to_the_group_and_unknown_group_is_404(client, g):
    d = g["d"]
    assert client.post(f"/groups/{g['gid']}/expenses", json=equal_body(d, [d]), headers=h(d)).status_code == 403
    assert client.post(f"/groups/{uuid.uuid4()}/expenses", json=equal_body(d, [d]), headers=h(d)).status_code == 404
    assert client.post(f"/groups/{g['gid']}/expenses", json=equal_body(d, [d])).status_code == 401


def test_payer_or_participant_outside_the_group_is_422(client, g):
    a, b, d = g["a"], g["b"], g["d"]
    for payload in (equal_body(a, [a, d]), {**equal_body(a, [a, b]), "payers": [{"user_id": uid(d),
                                                                                  "paid_amount_minor": 10000}]}):
        r = client.post(f"/groups/{g['gid']}/expenses", json=payload, headers=h(a))
        assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"
        assert r.json()["details"]["user_ids"] == [uid(d)]


def test_departed_member_cannot_be_added_to_a_new_expense(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    assert client.delete(f"/groups/{g['gid']}/members/me", headers=h(c)).status_code == 204
    r = client.post(f"/groups/{g['gid']}/expenses", json=equal_body(a, [a, c]), headers=h(a))
    assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"


def test_remainder_follows_the_group_join_order_not_the_request_order(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(c, 100)], "equal", [(c, None), (b, None), (a, None)], 100))
    assert [s["user_id"] for s in e["splits"]] == [uid(a), uid(b), uid(c)] and owed(e) == [34, 33, 33]


def test_payer_not_in_split_has_no_split_row(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(a, 9000)], "equal", [(b, None), (c, None)], 9000))
    assert owed(e) == [4500, 4500] and e["my_net"]["amount_minor"] == 9000  # vector 5


def test_group_expense_does_not_need_the_creator_to_take_part(client, g):
    a, b, c = g["a"], g["b"], g["c"]
    e = create_group_expense(client, a, g["gid"], body([(b, 1000)], "equal", [(b, None), (c, None)], 1000))
    assert e["my_net"]["amount_minor"] == 0 and e["created_by"] == uid(a)


# ---- non-group rules -----------------------------------------------------------------------------------------------

def test_non_group_without_the_creator_is_current_user_not_involved(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    for email in ("ravi@example.com", "meera@example.com"):
        client.post("/friends", json={"email": email}, headers=h(a))
    r = client.post("/expenses", json=equal_body(b, [b, c]), headers=h(a))
    assert r.status_code == 422 and r.json()["code"] == "CURRENT_USER_NOT_INVOLVED"


def test_non_group_with_a_stranger_is_participant_not_member(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    r = client.post("/expenses", json=equal_body(a, [a, b]), headers=h(a))
    assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"
    assert r.json()["details"]["user_ids"] == [uid(b)]


def test_non_group_with_an_implicit_friend_from_a_shared_group_is_allowed(client, g):
    e = create_expense(client, g["a"], equal_body(g["a"], [g["a"], g["b"]]))
    assert e["group_id"] is None


def test_non_group_canonical_order_is_creator_first_then_ascending_user_id(client):
    users = [user(client, n) for n in ("Asha", "Ravi", "Meera")]
    a = users[0]
    for email in ("ravi@example.com", "meera@example.com"):
        client.post("/friends", json={"email": email}, headers=h(a))
    others = sorted(users[1:], key=uid)
    e = create_expense(client, a, equal_body(a, [others[1], a, others[0]], total=100))
    assert [s["user_id"] for s in e["splits"]] == [uid(a), uid(others[0]), uid(others[1])]
    assert owed(e) == [34, 33, 33]


def test_non_group_expense_is_visible_to_participants_only(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a))
    e = create_expense(client, a, equal_body(a, [a, b]))
    assert client.get(f"/expenses/{e['id']}", headers=h(b)).status_code == 200
    r = client.get(f"/expenses/{e['id']}", headers=h(c))
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"


# ---- validation ----------------------------------------------------------------------------------------------------

def post(client, who, gid, payload):
    return client.post(f"/groups/{gid}/expenses", json=payload, headers=h(who))


def test_amount_bounds(client, g):
    a, b = g["a"], g["b"]
    for total in (0, -1, 10_000_000_000):
        r = post(client, a, g["gid"], equal_body(a, [a, b], total=total))
        assert r.status_code == 422, (total, r.text)
        assert r.json()["code"] in ("AMOUNT_OUT_OF_RANGE", "VALIDATION_ERROR")
    r = post(client, a, g["gid"], {**equal_body(a, [a, b], total=0), "payers": [{"user_id": uid(a),
                                                                                  "paid_amount_minor": 1}]})
    assert r.json()["code"] == "AMOUNT_OUT_OF_RANGE"
    r = post(client, a, g["gid"], equal_body(a, [a, b], total=10_000_000_000))
    assert r.json()["code"] == "AMOUNT_OUT_OF_RANGE"
    ok = post(client, a, g["gid"], equal_body(a, [a, b], total=9_999_999_999))
    assert ok.status_code == 201 and sum(owed(ok.json())) == 9_999_999_999  # vector 34


def test_money_must_be_an_integer(client, g):
    a, b = g["a"], g["b"]
    for bad in (100.5, 100.0, "100", True):
        p = equal_body(a, [a, b])
        p["total"]["amount_minor"] = bad
        assert post(client, a, g["gid"], p).status_code == 422
    p = equal_body(a, [a, b])
    p["payers"][0]["paid_amount_minor"] = 10000.0
    assert post(client, a, g["gid"], p).status_code == 422
    p = equal_body(a, [a, b])
    p["split"] = {"type": "exact", "entries": [{"user_id": uid(a), "value": 5000.0}, {"user_id": uid(b), "value": 5000}]}
    assert post(client, a, g["gid"], p).status_code == 422


def test_unknown_currency_and_category(client, g):
    a, b = g["a"], g["b"]
    r = post(client, a, g["gid"], equal_body(a, [a, b], currency="ZZZ"))
    assert r.status_code == 422 and r.json()["code"] == "CURRENCY_UNKNOWN"
    r = post(client, a, g["gid"], {**equal_body(a, [a, b]), "category_id": 9999})
    assert r.status_code == 422 and r.json()["details"]["fields"][0]["field"] == "category_id"
    assert post(client, a, g["gid"], {**equal_body(a, [a, b]), "category_id": 12}).json()["category_id"] == 12


def test_description_rules(client, g):
    a, b = g["a"], g["b"]
    for bad in ("", "   ", "x" * 201):
        assert post(client, a, g["gid"], equal_body(a, [a, b], description=bad)).status_code == 422
    assert post(client, a, g["gid"], equal_body(a, [a, b], description="  Tea  ")).json()["description"] == "Tea"
    assert post(client, a, g["gid"], equal_body(a, [a, b], description="x" * 200)).status_code == 201
    r = post(client, a, g["gid"], {**equal_body(a, [a, b]), "notes": "n" * 2001})
    assert r.status_code == 422
    assert post(client, a, g["gid"], {**equal_body(a, [a, b]), "notes": "ok"}).json()["notes"] == "ok"


@pytest.mark.parametrize("split_type,entries,total,code,details", [
    ("exact", [("a", 5000), ("b", 3000), ("c", 1000)], 10000, "SPLIT_SUM_MISMATCH",
     {"expected": 10000, "actual": 9000, "difference": -1000}),
    ("percent", [("a", 5000), ("b", 4900)], 10000, "SPLIT_PERCENT_MISMATCH", {"difference_bp": -100}),
    ("shares", [("a", 0), ("b", 0)], 10000, "SPLIT_NO_SHARES", None),
    ("adjustment", [("a", 6000), ("b", 5000), ("c", 0)], 10000, "SPLIT_ADJUSTMENT_EXCEEDS_TOTAL",
     {"expected": 10000, "actual": 11000, "difference": 1000}),
    ("equal", [("a", None), ("a", None)], 10000, "DUPLICATE_PARTICIPANT", None),
])
def test_split_errors_carry_the_documented_details(client, g, split_type, entries, total, code, details):
    a = g["a"]
    payload = body([(a, total)], split_type, [(g[k], v) for k, v in entries], total)
    r = post(client, a, g["gid"], payload)
    assert r.status_code == 422 and r.json()["code"] == code, r.text
    assert r.json().get("details") == details
    assert client.get(f"/groups/{g['gid']}/expenses", headers=h(a)).json()["items"] == []  # nothing stored


def test_duplicate_payer_and_empty_lists(client, g):
    a, b = g["a"], g["b"]
    r = post(client, a, g["gid"], body([(a, 5000), (a, 5000)], "equal", [(a, None), (b, None)], 10000))
    assert r.status_code == 422 and r.json()["code"] == "DUPLICATE_PAYER"
    p = equal_body(a, [a, b])
    assert post(client, a, g["gid"], {**p, "payers": []}).status_code == 422
    assert post(client, a, g["gid"], {**p, "split": {"type": "equal", "entries": []}}).status_code == 422
    assert post(client, a, g["gid"], {**p, "split": {"type": "itemized", "entries": [{"user_id": uid(a)}]}}
                ).status_code == 422
    assert post(client, a, g["gid"], {**p, "payers": [{"user_id": uid(a), "paid_amount_minor": 0}]}).status_code == 422


def test_split_value_ranges(client, g):
    a, b = g["a"], g["b"]
    assert post(client, a, g["gid"], body([(a, 100)], "shares", [(a, 1000), (b, 1)], 100)).status_code == 422
    assert post(client, a, g["gid"], body([(a, 100)], "percent", [(a, 10001), (b, 0)], 100)).status_code == 422
    assert post(client, a, g["gid"], body([(a, 100)], "exact", [(a, -1), (b, 101)], 100)).status_code == 422


def test_recurrence_is_not_implemented_yet(client, g):
    a, b = g["a"], g["b"]
    p = {**equal_body(a, [a, b]), "recurrence": {"interval": "monthly", "reminder_days_before": 2}}
    r = post(client, a, g["gid"], p)
    assert r.status_code == 501 and r.json()["code"] == "NOT_IMPLEMENTED"
    assert client.get(f"/groups/{g['gid']}/expenses", headers=h(a)).json()["items"] == []
    assert client.post("/expenses", json={**p, "group_id": g["gid"]}, headers=h(a)).status_code == 501
    assert post(client, a, g["gid"], {**equal_body(a, [a, b]), "recurrence": None}).status_code == 201


# ---- idempotency ---------------------------------------------------------------------------------------------------

def test_same_idempotency_key_twice_makes_one_row_and_replays_the_response(client, db_session, g):
    a, b = g["a"], g["b"]
    key = str(uuid.uuid4())
    payload = equal_body(a, [a, b])
    r1 = client.post(f"/groups/{g['gid']}/expenses", json=payload, headers={**h(a), "Idempotency-Key": key})
    r2 = client.post(f"/groups/{g['gid']}/expenses", json=payload, headers={**h(a), "Idempotency-Key": key})
    assert r1.status_code == r2.status_code == 201 and r1.json() == r2.json()
    assert count_expenses(db_session) == 1
    stored = db_session.scalar(select(Expense.idempotency_key))
    assert str(stored) == key


def test_idempotency_key_on_post_expenses_and_scoping(client, db_session, g):
    a, b = g["a"], g["b"]
    key = str(uuid.uuid4())
    hdr = {**h(a), "Idempotency-Key": key}
    r1 = client.post("/expenses", json={**equal_body(a, [a, b]), "group_id": g["gid"]}, headers=hdr)
    r2 = client.post("/expenses", json={**equal_body(a, [a, b]), "group_id": g["gid"]}, headers=hdr)
    assert r1.status_code == 201 and r1.json() == r2.json() and count_expenses(db_session) == 1
    other = client.post(f"/groups/{g['gid']}/expenses", json=equal_body(a, [a, b]), headers=hdr)  # other endpoint
    assert other.status_code == 422 and other.json()["code"] == "VALIDATION_ERROR"
    assert count_expenses(db_session) == 1
    # another user may reuse the same key value
    r3 = client.post(f"/groups/{g['gid']}/expenses", json=equal_body(b, [a, b]), headers={**h(b), "Idempotency-Key": key})
    assert r3.status_code == 201 and count_expenses(db_session) == 2
    assert client.post("/expenses", json=equal_body(a, [a]), headers={**h(a), "Idempotency-Key": "nope"}
                       ).status_code == 422


def test_failed_request_does_not_burn_the_idempotency_key(client, db_session, g):
    a, b = g["a"], g["b"]
    key = str(uuid.uuid4())
    hdr = {**h(a), "Idempotency-Key": key}
    bad = client.post(f"/groups/{g['gid']}/expenses", json=equal_body(a, [a, b], total=0), headers=hdr)
    assert bad.status_code == 422
    good = client.post(f"/groups/{g['gid']}/expenses", json=equal_body(a, [a, b]), headers=hdr)
    assert good.status_code == 201 and count_expenses(db_session) == 1


# ---- reading and listing -------------------------------------------------------------------------------------------

def test_get_expense_auth_and_errors(client, g):
    a, d = g["a"], g["d"]
    e = create_group_expense(client, a, g["gid"], equal_body(a, [a, g["b"]]))
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e
    assert client.get(f"/expenses/{e['id']}", headers=h(g["c"])).status_code == 200  # any group member
    assert client.get(f"/expenses/{e['id']}", headers=h(d)).status_code == 403
    assert client.get(f"/expenses/{uuid.uuid4()}", headers=h(a)).status_code == 404
    assert client.get(f"/expenses/{e['id']}").status_code == 401
    assert client.get("/expenses/not-a-uuid", headers=h(a)).status_code == 422


def test_member_who_left_cannot_read_group_expenses(client, g):
    e = create_group_expense(client, g["a"], g["gid"], equal_body(g["a"], [g["a"], g["b"]]))
    assert client.delete(f"/groups/{g['gid']}/members/me", headers=h(g["c"])).status_code == 204
    assert client.get(f"/expenses/{e['id']}", headers=h(g["c"])).status_code == 403
    assert client.get(f"/groups/{g['gid']}/expenses", headers=h(g["c"])).status_code == 403


def test_group_list_order_paging_and_deleted(client, db_session, g):
    a, b = g["a"], g["b"]
    made = {}
    for name, date in (("old", "2026-11-01"), ("mid", "2026-11-03"), ("new", "2026-11-05"), ("mid2", "2026-11-03")):
        made[name] = create_group_expense(client, a, g["gid"], equal_body(a, [a, b], description=name, date=date))
    r = client.get(f"/groups/{g['gid']}/expenses", headers=h(b))
    assert r.status_code == 200 and r.json()["next_cursor"] is None
    names = [i["description"] for i in r.json()["items"]]
    assert names == ["new", "mid2", "mid", "old"]  # date desc, then created_at desc
    # page through two at a time
    seen, cursor = [], None
    for _ in range(5):
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get(f"/groups/{g['gid']}/expenses", params=params, headers=h(a)).json()
        seen += [i["description"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == names
    assert client.delete(f"/expenses/{made['mid']['id']}", headers=h(a)).status_code == 200
    live = client.get(f"/groups/{g['gid']}/expenses", headers=h(a)).json()["items"]
    assert [i["description"] for i in live] == ["new", "mid2", "old"]
    every = client.get(f"/groups/{g['gid']}/expenses", params={"include_deleted": "true"}, headers=h(a)).json()["items"]
    assert [i["description"] for i in every] == names and every[2]["deleted_at"] is not None
    assert client.get(f"/groups/{g['gid']}/expenses", headers=h(g["d"])).status_code == 403
    assert client.get(f"/groups/{uuid.uuid4()}/expenses", headers=h(a)).status_code == 404
    assert client.get(f"/groups/{g['gid']}/expenses", params={"cursor": "zzz"}, headers=h(a)).status_code == 422
    assert client.get(f"/groups/{g['gid']}/expenses", params={"limit": 0}, headers=h(a)).status_code == 422


def test_list_is_ordered_by_created_at_then_id_when_dates_tie(client, db_session, g):
    from datetime import datetime, timezone
    a, b = g["a"], g["b"]
    ids = [create_group_expense(client, a, g["gid"], equal_body(a, [a, b], description=str(i)))["id"]
           for i in range(4)]
    for i in ids:
        set_created_at(db_session, i, datetime(2026, 11, 5, 8, tzinfo=timezone.utc))  # identical created_at
    got = [i["id"] for i in client.get(f"/groups/{g['gid']}/expenses", headers=h(a)).json()["items"]]
    assert got == sorted(ids, reverse=True)
    paged = []
    cursor = None
    while True:
        page = client.get(f"/groups/{g['gid']}/expenses", params={"limit": 1, **({"cursor": cursor} if cursor else {})},
                          headers=h(a)).json()
        paged += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert paged == got


def test_list_expenses_scope_and_filters(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    for email in ("ravi@example.com", "meera@example.com"):
        client.post("/friends", json={"email": email}, headers=h(a))
    gid = make_group(client, a, [b])
    ge = create_group_expense(client, a, gid, equal_body(a, [a, b], description="group"))
    n_ab = create_expense(client, a, equal_body(a, [a, b], description="ab"))
    n_ac = create_expense(client, a, equal_body(a, [a, c], description="ac"))
    def ids(who, **params):
        r = client.get("/expenses", params=params, headers=h(who))
        assert r.status_code == 200, r.text
        return {i["id"] for i in r.json()["items"]}
    assert ids(a) == {ge["id"], n_ab["id"], n_ac["id"]}
    assert ids(b) == {ge["id"], n_ab["id"]}
    assert ids(c) == {n_ac["id"]}  # not in the group: only the non-group expense she takes part in
    assert ids(a, non_group="true") == {n_ab["id"], n_ac["id"]}
    assert ids(a, non_group="false") == {ge["id"]}
    assert ids(a, friend_user_id=uid(b)) == {ge["id"], n_ab["id"]}
    assert ids(a, friend_user_id=uid(c)) == {n_ac["id"]}
    assert ids(a, friend_user_id=uid(c), non_group="false") == set()
    assert ids(b, friend_user_id=uid(c)) == set()  # nothing shared that B can see
    # deleted expenses and deleted groups drop out
    client.delete(f"/expenses/{n_ab['id']}", headers=h(a))
    assert ids(a) == {ge["id"], n_ac["id"]}
    assert client.delete(f"/groups/{gid}", headers=h(a)).status_code == 204
    assert ids(a) == {n_ac["id"]}


def test_list_expenses_paging_and_params(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a))
    made = [create_expense(client, a, equal_body(a, [a, b], description=str(i), date=f"2026-11-0{i + 1}"))["id"]
            for i in range(5)]
    seen, cursor = [], None
    while True:
        page = client.get("/expenses", params={"limit": 2, **({"cursor": cursor} if cursor else {})},
                          headers=h(a)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == made[::-1]
    assert client.get("/expenses", params={"limit": 101}, headers=h(a)).status_code == 422
    assert client.get("/expenses", params={"cursor": "bad"}, headers=h(a)).status_code == 422
    assert client.get("/expenses", params={"friend_user_id": "x"}, headers=h(a)).status_code == 422
    assert client.get("/expenses").status_code == 401


def test_search_is_not_available_yet(client):
    a = user(client, "Asha")
    r = client.get("/expenses", params={"q": "goa"}, headers=h(a))
    assert r.status_code == 501 and r.json()["code"] == "NOT_IMPLEMENTED"
    assert client.get("/expenses", params={"q": "g"}, headers=h(a)).status_code == 422


# ---- contract ------------------------------------------------------------------------------------------------------

def test_responses_validate_against_the_openapi_schemas(client, g):
    call = Caller(client)
    a, b = g["a"], g["b"]
    tok = a["access_token"]
    payload = equal_body(a, [a, b])
    created = call("POST", f"/groups/{g['gid']}/expenses", 201, token=tok, json_body=payload).json()
    call("POST", "/expenses", 201, token=tok, json_body={**payload, "group_id": g["gid"]})
    call("POST", f"/groups/{g['gid']}/expenses", 422, token=tok, json_body=equal_body(a, [a, b], total=0))
    call("POST", f"/groups/{g['gid']}/expenses", 403, token=g["d"]["access_token"], json_body=payload)
    call("GET", f"/expenses/{created['id']}", 200, token=tok)
    call("GET", f"/expenses/{created['id']}", 403, token=g["d"]["access_token"])
    call("GET", f"/expenses/{uuid.uuid4()}", 404, token=tok)
    call("GET", f"/groups/{g['gid']}/expenses", 200, token=tok, params={"limit": 1})
    call("GET", "/expenses", 200, token=tok, params={"non_group": "false"})
    call("PATCH", f"/expenses/{created['id']}", 200, token=tok,
         json_body={"version": 1, "description": "renamed"})
    call("PATCH", f"/expenses/{created['id']}", 409, token=tok, json_body={"version": 1, "description": "again"})
    call("DELETE", f"/expenses/{created['id']}", 200, token=tok)
    call("DELETE", f"/expenses/{created['id']}", 409, token=tok)
    call("POST", f"/expenses/{created['id']}/restore", 200, token=tok)
    call("POST", f"/expenses/{created['id']}/restore", 409, token=tok)
    call("POST", f"/expenses/{created['id']}/comments", 201, token=tok, json_body={"body": "hi"})
    call("GET", f"/expenses/{created['id']}/comments", 200, token=tok)
    call("GET", f"/groups/{g['gid']}/timeline", 200, token=tok)
