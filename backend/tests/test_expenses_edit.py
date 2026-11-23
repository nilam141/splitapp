"""S3-B-4: PATCH/DELETE/restore, departed-member guard, system comments, currency immutability, friend removal."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Comment, Expense
from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user


@pytest.fixture()
def g(client):
    a, b, c, d = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev"))
    gid = make_group(client, a, [b, c])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b, c], description="Groceries"))  # 3334/3333/3333
    return {"a": a, "b": b, "c": c, "d": d, "gid": gid, "e": e}


def patch(client, who, e, **fields):
    return client.patch(f"/expenses/{e['id']}", json={"version": e["version"], **fields}, headers=h(who))


def comments(client, who, e):
    return client.get(f"/expenses/{e['id']}/comments", headers=h(who)).json()["items"]


def split_pairs(e):
    return [(s["user_id"], s["owed_amount_minor"]) for s in e["splits"]]


# ---- edit: FLOW-04 ---------------------------------------------------------------------------------------------------

def test_flow_04_edit_total_by_a_non_creator_resplits_and_writes_one_system_comment(client, g):
    a, b, c, e = g["a"], g["b"], g["c"], g["e"]
    r = patch(client, b, e, total={"amount_minor": 12000, "currency": "INR"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["version"] == 2 and got["total"]["amount_minor"] == 12000
    assert [s["owed_amount_minor"] for s in got["splits"]] == [4000, 4000, 4000]
    assert got["payers"] == [{"user_id": uid(a), "paid_amount_minor": 12000}]  # single payer follows the total
    assert got["updated_by"] == uid(b) and got["created_by"] == uid(a)
    assert got["my_net"]["amount_minor"] == -4000
    items = comments(client, a, got)
    assert len(items) == 1 and items[0]["kind"] == "system" and items[0]["user"] is None
    assert items[0]["body"] == "total 100.00 → 120.00"
    assert got["comment_count"] == 1
    assert client.get(f"/expenses/{e['id']}", headers=h(c)).json()["version"] == 2


def test_system_comment_uses_the_currency_exponent(client, g):
    a, b = g["a"], g["b"]
    jpy = create_group_expense(client, a, g["gid"], equal_body(a, [a, b], total=1000, currency="JPY"))
    kwd = create_group_expense(client, a, g["gid"], equal_body(a, [a, b], total=1500, currency="KWD"))
    assert comments(client, a, patch(client, a, jpy, total={"amount_minor": 1500, "currency": "JPY"}).json()
                    )[0]["body"] == "total 1000 → 1500"
    assert comments(client, a, patch(client, a, kwd, total={"amount_minor": 1234567, "currency": "kwd"}).json()
                    )[0]["body"] == "total 1.500 → 1234.567"


def test_edits_that_do_not_touch_the_total_write_no_comment(client, g):
    a, e = g["a"], g["e"]
    r = patch(client, a, e, description="Veg", notes="n", category_id=12, expense_date="2026-11-07")
    assert r.status_code == 200
    got = r.json()
    assert (got["description"], got["notes"], got["category_id"], got["expense_date"], got["version"]) == \
           ("Veg", "n", 12, "2026-11-07", 2)
    assert comments(client, a, got) == []
    cleared = patch(client, a, got, notes=None).json()
    assert cleared["notes"] is None and cleared["version"] == 3


def test_noop_patch_changes_nothing(client, g):
    a, e = g["a"], g["e"]
    r = patch(client, a, e, description="Groceries", total=e["total"])
    assert r.status_code == 200 and r.json() == e and r.json()["version"] == 1
    assert comments(client, a, e) == []


def test_stale_version_is_409_with_current_version(client, g):
    a, e = g["a"], g["e"]
    assert patch(client, a, e, description="first").status_code == 200
    r = patch(client, a, e, description="second")  # still version 1
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert r.json()["details"] == {"current_version": 2}
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["description"] == "first"


def test_patch_changing_the_currency_is_422(client, g):
    a, e = g["a"], g["e"]
    r = patch(client, a, e, total={"amount_minor": 10000, "currency": "USD"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["details"]["fields"][0]["field"] == "total.currency"
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e


def test_patch_payers_and_split_are_revalidated_against_the_total(client, g):
    a, b, c, e = g["a"], g["b"], g["c"], g["e"]
    r = patch(client, a, e, split={"type": "exact", "entries": [{"user_id": uid(a), "value": 9000},
                                                                {"user_id": uid(b), "value": 500}]})
    assert r.status_code == 422 and r.json()["code"] == "SPLIT_SUM_MISMATCH"
    assert r.json()["details"] == {"expected": 10000, "actual": 9500, "difference": -500}
    r = patch(client, a, e, payers=[{"user_id": uid(a), "paid_amount_minor": 6000},
                                    {"user_id": uid(b), "paid_amount_minor": 3000}])
    assert r.status_code == 422 and r.json()["code"] == "PAYER_SUM_MISMATCH"
    r = patch(client, a, e, payers=[{"user_id": uid(a), "paid_amount_minor": 6000},
                                    {"user_id": uid(b), "paid_amount_minor": 4000}],
              split={"type": "shares", "entries": [{"user_id": uid(a), "value": 1}, {"user_id": uid(b), "value": 1}]})
    assert r.status_code == 200
    got = r.json()
    assert got["split_type"] == "shares" and split_pairs(got) == [(uid(a), 5000), (uid(b), 5000)]
    assert sorted(p["paid_amount_minor"] for p in got["payers"]) == [4000, 6000]
    assert comments(client, a, got) == []  # total unchanged: no system comment


def test_patch_new_participants_must_be_group_members(client, g):
    a, d, e = g["a"], g["d"], g["e"]
    r = patch(client, a, e, split={"type": "equal", "entries": [{"user_id": uid(a)}, {"user_id": uid(d)}]})
    assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"


def test_patch_total_only_on_non_equal_expenses(client, g):
    """Documented decision: stored payers/splits are re-validated against the new total; percent, shares and
    adjustment re-compute from their inputs, an exact split or a multi-payer set that no longer adds up is a 422."""
    a, b, c = g["a"], g["b"], g["c"]
    pct = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b], total=1000), "split": {
        "type": "percent", "entries": [{"user_id": uid(a), "value": 3333}, {"user_id": uid(b), "value": 6667}]}})
    got = patch(client, a, pct, total={"amount_minor": 3000, "currency": "INR"}).json()
    assert split_pairs(got) == [(uid(a), 1000), (uid(b), 2000)]  # 33.33% / 66.67% of 3000 (999.9 -> 1000)
    ex = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b], total=1000), "split": {
        "type": "exact", "entries": [{"user_id": uid(a), "value": 400}, {"user_id": uid(b), "value": 600}]}})
    r = patch(client, a, ex, total={"amount_minor": 2000, "currency": "INR"})
    assert r.status_code == 422 and r.json()["code"] == "SPLIT_SUM_MISMATCH"
    multi = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b], total=1000), "payers": [
        {"user_id": uid(a), "paid_amount_minor": 600}, {"user_id": uid(b), "paid_amount_minor": 400}]})
    r = patch(client, a, multi, total={"amount_minor": 2000, "currency": "INR"})
    assert r.status_code == 422 and r.json()["code"] == "PAYER_SUM_MISMATCH"
    assert r.json()["details"] == {"expected": 2000, "actual": 1000, "difference": -1000}
    assert client.get(f"/expenses/{multi['id']}", headers=h(a)).json() == multi
    adj = create_group_expense(client, a, g["gid"], {**equal_body(a, [a, b], total=1000), "split": {
        "type": "adjustment", "entries": [{"user_id": uid(a), "value": 200}, {"user_id": uid(b), "value": 0}]}})
    after = patch(client, a, adj, total={"amount_minor": 2000, "currency": "INR"}).json()
    assert split_pairs(after) == [(uid(a), 1100), (uid(b), 900)]  # 200 extra for A, the other 1800 shared equally
    r = patch(client, a, after, total={"amount_minor": 100, "currency": "INR"})
    assert r.status_code == 422 and r.json()["code"] == "SPLIT_ADJUSTMENT_EXCEEDS_TOTAL"


def test_patch_validation_and_auth(client, g):
    a, d, e = g["a"], g["d"], g["e"]
    assert patch(client, d, e, description="x").status_code == 403  # not a group member
    assert client.patch(f"/expenses/{uuid.uuid4()}", json={"version": 1}, headers=h(a)).status_code == 404
    assert client.patch(f"/expenses/{e['id']}", json={"version": 1}).status_code == 401
    assert client.patch(f"/expenses/{e['id']}", json={"description": "x"}, headers=h(a)).status_code == 422  # no version
    for bad in ({"description": None}, {"description": ""}, {"description": "  "}, {"total": None},
                {"category_id": 9999}, {"total": {"amount_minor": 0, "currency": "INR"}},
                {"total": {"amount_minor": 10_000_000_000, "currency": "INR"}},
                {"total": {"amount_minor": 1.5, "currency": "INR"}}, {"split": None}, {"notes": "n" * 2001}):
        assert patch(client, a, e, **bad).status_code == 422, bad
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e


def test_patch_non_group_needs_the_creator_and_friends(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a))
    e = create_expense(client, a, equal_body(a, [a, b]))
    r = client.patch(f"/expenses/{e['id']}", headers=h(b), json={"version": 1, "split": {
        "type": "equal", "entries": [{"user_id": uid(b)}, {"user_id": uid(c)}]}, "payers": [
        {"user_id": uid(b), "paid_amount_minor": 10000}]})
    assert r.status_code == 422 and r.json()["code"] == "CURRENT_USER_NOT_INVOLVED"  # the creator A dropped out
    r = client.patch(f"/expenses/{e['id']}", headers=h(b), json={"version": 1, "split": {
        "type": "equal", "entries": [{"user_id": uid(a)}, {"user_id": uid(b)}, {"user_id": uid(c)}]}})
    assert r.status_code == 422 and r.json()["code"] == "PARTICIPANT_NOT_MEMBER"  # C is not B's friend
    ok = client.patch(f"/expenses/{e['id']}", headers=h(b), json={"version": 1, "total": {
        "amount_minor": 10001, "currency": "INR"}})
    assert ok.status_code == 200 and [s["owed_amount_minor"] for s in ok.json()["splits"]] == [5001, 5000]
    assert ok.json()["splits"][0]["user_id"] == uid(a)  # creator first even when B edits
    assert client.patch(f"/expenses/{e['id']}", headers=h(c), json={"version": 2, "description": "x"}
                        ).status_code == 403


# ---- departed member guard ---------------------------------------------------------------------------------------------

def test_edit_delete_and_restore_with_a_departed_participant_are_409_and_work_again_after_rejoin(client, g):
    """Revised 2026-11-11 (OQ-43, S4-Q-4): delete and restore are blocked too, like edit."""
    a, b, c, e = g["a"], g["b"], g["c"], g["e"]
    # C owes 3333 INR; settle C to 0 with an offsetting expense (C pays 3333, only A owes) so the OUTSTANDING_BALANCE guard lets C leave
    create_group_expense(client, a, g["gid"], equal_body(c, [a], total=3333, description="offset"))
    assert client.delete(f"/groups/{g['gid']}/members/me", headers=h(c)).status_code == 204
    r = patch(client, a, e, description="late edit")
    assert r.status_code == 409 and r.json()["code"] == "EXPENSE_HAS_DEPARTED_MEMBER"
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e
    r = client.delete(f"/expenses/{e['id']}", headers=h(a))
    assert r.status_code == 409 and r.json()["code"] == "EXPENSE_HAS_DEPARTED_MEMBER"
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e  # not deleted, version unchanged
    # rejoining clears left_at: delete and restore work again
    assert client.post(f"/groups/{g['gid']}/members", json={"user_ids": [uid(c)]}, headers=h(a)).status_code == 200
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200
    assert client.post(f"/expenses/{e['id']}/restore", headers=h(a)).status_code == 200
    # an expense that never involved the departed member stays editable
    other = create_group_expense(client, a, g["gid"], equal_body(a, [a, b], description="ab"))
    assert patch(client, a, other, description="fine").status_code == 200


def test_departed_payer_blocks_edit_and_delete(client, g):
    a, b = g["a"], g["b"]
    e = create_group_expense(client, a, g["gid"], {**equal_body(a, [a]), "payers": [
        {"user_id": uid(b), "paid_amount_minor": 10000}]})
    # B is owed 10000 minus 3333 owed in the fixture expense = 6667; A pays 6667 for B only, so B nets to 0
    create_group_expense(client, a, g["gid"], equal_body(a, [b], total=6667, description="offset"))
    assert client.delete(f"/groups/{g['gid']}/members/me", headers=h(b)).status_code == 204
    assert patch(client, a, e, description="x").json()["code"] == "EXPENSE_HAS_DEPARTED_MEMBER"
    r = client.delete(f"/expenses/{e['id']}", headers=h(a))
    assert r.status_code == 409 and r.json()["code"] == "EXPENSE_HAS_DEPARTED_MEMBER"  # S4-Q-4 (OQ-43)
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e
    assert client.post(f"/groups/{g['gid']}/members", json={"user_ids": [uid(b)]}, headers=h(a)).status_code == 200
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200
    assert client.post(f"/expenses/{e['id']}/restore", headers=h(a)).status_code == 200


# ---- delete and restore --------------------------------------------------------------------------------------------------

def test_delete_restore_cycle(client, g):
    a, b, e = g["a"], g["b"], g["e"]
    r = client.delete(f"/expenses/{e['id']}", headers=h(b))
    assert r.status_code == 200
    gone = r.json()
    assert gone["deleted_at"] is not None and gone["deleted_by"] == uid(b) and gone["version"] == 2
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["deleted_at"] is not None  # readable, flagged
    again = client.delete(f"/expenses/{e['id']}", headers=h(a))
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_DELETED"
    assert patch(client, a, gone, description="x").json()["code"] == "ALREADY_DELETED"
    back = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert back.status_code == 200 and back.json()["deleted_at"] is None and back.json()["deleted_by"] is None
    assert back.json()["version"] == 3 and split_pairs(back.json()) == split_pairs(e)
    nd = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert nd.status_code == 409 and nd.json()["code"] == "NOT_DELETED"


def test_delete_and_restore_auth(client, g):
    d, e = g["d"], g["e"]
    assert client.delete(f"/expenses/{e['id']}", headers=h(d)).status_code == 403
    assert client.post(f"/expenses/{e['id']}/restore", headers=h(d)).status_code == 403
    assert client.delete(f"/expenses/{uuid.uuid4()}", headers=h(d)).status_code == 404
    assert client.post(f"/expenses/{uuid.uuid4()}/restore", headers=h(d)).status_code == 404
    assert client.delete(f"/expenses/{e['id']}").status_code == 401
    assert client.post(f"/expenses/{e['id']}/restore").status_code == 401


# ---- friend removal (OQ-32) -----------------------------------------------------------------------------------------------

def _deleted(db_session, expense_id):
    db_session.expire_all()
    return db_session.scalar(select(Expense.deleted_at).where(Expense.id == uuid.UUID(expense_id)))


def test_removing_a_friend_soft_deletes_only_the_pairs_non_group_expenses(client, db_session):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    for email in ("ravi@example.com", "meera@example.com"):
        client.post("/friends", json={"email": email}, headers=h(a))
    client.post("/friends", json={"email": "meera@example.com"}, headers=h(b))
    pair = [create_expense(client, a, equal_body(a, [a, b], total=6000)),            # B owes A 3000
            create_expense(client, b, equal_body(b, [a, b], total=900, description="back"))]  # A owes B 450
    one_way = create_expense(client, a, {**equal_body(a, [b]), "payers": [{"user_id": uid(a), "paid_amount_minor": 10000}]})
    solo = create_expense(client, a, equal_body(a, [a]))                               # only A: not "between" A and B
    with_c = create_expense(client, a, equal_body(a, [a, c]))
    three = create_expense(client, a, equal_body(a, [a, b, c]))                       # A, B and C: untouched
    gone_already = create_expense(client, a, equal_body(a, [a, b], description="old"))
    assert client.delete(f"/expenses/{gone_already['id']}", headers=h(a)).status_code == 200
    before = _deleted(db_session, gone_already["id"])

    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204

    assert all(_deleted(db_session, e["id"]) is not None for e in (*pair, one_way))
    assert all(_deleted(db_session, e["id"]) is None for e in (solo, with_c, three))
    assert _deleted(db_session, gone_already["id"]) == before  # an already deleted one keeps its original stamp
    got = client.get(f"/expenses/{pair[0]['id']}", headers=h(a)).json()
    assert got["deleted_by"] == uid(a) and got["version"] == 2
    listing = client.get("/expenses", params={"non_group": "true"}, headers=h(a)).json()["items"]
    assert {i["id"] for i in listing} == {solo["id"], with_c["id"], three["id"]}


def test_removing_a_friend_leaves_group_expenses_alone(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    ge = create_group_expense(client, a, gid, equal_body(a, [a, b], total=6000))
    # B owes 3000; B pays 3000 for A so B is at 0 and may leave
    create_group_expense(client, a, gid, equal_body(b, [a], total=3000, description="offset"))
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204  # now explicit friends (10.1a)
    ng = create_expense(client, a, equal_body(a, [a, b], total=6000))
    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204
    assert _deleted(db_session, ng["id"]) is not None and _deleted(db_session, ge["id"]) is None


def test_refused_friend_removal_deletes_nothing(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    ng = create_expense(client, a, equal_body(a, [a, b]))
    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 409  # shared group
    assert _deleted(db_session, ng["id"]) is None
    assert gid
