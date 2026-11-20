"""S4-Q-1 (API level) and S4-B-2 / S4-B-3 definitions of done: group balances, simplify toggle, friend balances,
breakdown, settled_up_since, GET /balances, the OUTSTANDING_BALANCE guard (vector 35), vector 33 (delete/restore).

Written before S4-B-2 / S4-B-3. Today the balance fields are [] / null, GET /groups/{id}/balances and GET /balances
are 404 and the guard is stubbed, so each test fails on the first value assertion (a status 404 or an empty balance
list), not on setup. Setup uses only S3 endpoints. Integer minor units only. A line with amount 0 is treated as absent
(`lines()` drops zeros) because the contract does not say whether zero lines are listed.
"""
import pytest
from datetime import datetime, timedelta, timezone

from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, set_created_at, uid, user


def lines(bal):
    """BalanceLine list -> {currency: amount_minor} without zero lines."""
    out = {}
    for x in bal:
        assert set(x) >= {"amount_minor", "currency"}
        assert type(x["amount_minor"]) is int
        if x["amount_minor"] != 0:
            assert x["currency"] not in out, "one line per currency"
            out[x["currency"]] = x["amount_minor"]
    return out


def exact_body(payer, debts, currency="INR", total=None, **extra):
    """`payer` paid everything; `debts` = [(user, owed)] is an exact split (payer need not be in it)."""
    total = total if total is not None else sum(v for _, v in debts)
    return {"description": "Item", "total": {"amount_minor": total, "currency": currency}, "expense_date": "2026-11-05",
            "payers": [{"user_id": uid(payer), "paid_amount_minor": total}],
            "split": {"type": "exact", "entries": [{"user_id": uid(u), "value": v} for u, v in debts]}, **extra}


def owes(client, creditor, gid, debtor, amount, currency="INR", who=None):
    """Group expense creating `debtor owes creditor amount`."""
    return create_group_expense(client, who or creditor, gid, exact_body(creditor, [(debtor, amount)], currency))


def nongroup_owes(client, creditor, debtor, amount, currency="INR", who=None):
    body = exact_body(creditor, [(debtor, amount)], currency)
    body["group_id"] = None
    return create_expense(client, who or creditor, body)


def group_balances(client, who, gid):
    r = client.get(f"/groups/{gid}/balances", headers=h(who))
    assert r.status_code == 200, f"GET /groups/{{id}}/balances -> {r.status_code} (needs S4-B-2): {r.text}"
    return r.json()


def member_lines(body):
    return {m["user_id"]: lines(m["balances"]) for m in body["members"]}


def tr(body):
    return [(t["from_user_id"], t["to_user_id"], t["amount_minor"], t["currency"]) for t in body["transfers"]]


def set_simplify(client, who, gid, value):
    v = client.get(f"/groups/{gid}", headers=h(who)).json()["version"]
    r = client.patch(f"/groups/{gid}", json={"version": v, "simplify_debts": value}, headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def flat(client):
    """Flat 4B: A (creator, canonical first), B, C. FLOW-03a: A pays 10000 equal over A, B, C -> 3334/3333/3333."""
    a, b, c, z = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Zed"))
    gid = make_group(client, a, [b, c], "Flat 4B")
    e = create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=10000, description="Groceries"))
    return {"a": a, "b": b, "c": c, "z": z, "gid": gid, "e": e}


@pytest.fixture()
def chain(client):
    """A owes B 1000 and B owes C 1000 (vector 19/21): nets A -1000, B 0, C +1000, simplify on (default)."""
    a, b, c = (user(client, n) for n in ("Asha", "Ravi", "Meera"))
    gid = make_group(client, a, [b, c], "Chain")
    owes(client, b, gid, a, 1000)
    owes(client, c, gid, b, 1000)
    return {"a": a, "b": b, "c": c, "gid": gid}


# ---- S4-B-2: Flat 4B ----------------------------------------------------------------------------------------------

def test_flat_4b_nets_and_transfers_after_03a(client, flat):
    a, b, c, gid = flat["a"], flat["b"], flat["c"], flat["gid"]
    body = group_balances(client, b, gid)  # any member may read
    assert body["group_id"] == gid and body["simplified"] is True
    assert [m["user_id"] for m in body["members"]] == [uid(a), uid(b), uid(c)]  # canonical order
    assert member_lines(body) == {uid(a): {"INR": 6666}, uid(b): {"INR": -3333}, uid(c): {"INR": -3333}}
    assert tr(body) == [(uid(b), uid(a), 3333, "INR"), (uid(c), uid(a), 3333, "INR")]
    assert sum(sum(m.values()) for m in member_lines(body).values()) == 0


def test_flat_4b_same_for_every_member_and_pairwise_matches_when_simplify_off(client, flat):
    set_simplify(client, flat["a"], flat["gid"], False)
    for who in (flat["a"], flat["b"], flat["c"]):
        body = group_balances(client, who, flat["gid"])
        assert body["simplified"] is False
        assert tr(body) == [(uid(flat["b"]), uid(flat["a"]), 3333, "INR"), (uid(flat["c"]), uid(flat["a"]), 3333, "INR")]


def test_toggle_changes_transfers_not_members(client, chain):
    a, b, c, gid = chain["a"], chain["b"], chain["c"], chain["gid"]
    on = group_balances(client, a, gid)
    assert on["simplified"] is True
    assert tr(on) == [(uid(a), uid(c), 1000, "INR")]                                  # vector 19
    set_simplify(client, a, gid, False)
    off = group_balances(client, a, gid)
    assert off["simplified"] is False
    assert tr(off) == [(uid(a), uid(b), 1000, "INR"), (uid(b), uid(c), 1000, "INR")]   # vector 21
    assert off["members"] == on["members"]                                               # same nets, same order
    assert member_lines(on) == {uid(a): {"INR": -1000}, uid(b): {}, uid(c): {"INR": 1000}}
    set_simplify(client, a, gid, True)
    assert group_balances(client, a, gid) == on


def test_group_balances_per_currency_never_summed_vector_28(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    owes(client, a, gid, b, 1000, "INR")
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=1000, currency="USD"))
    body = group_balances(client, a, gid)
    assert member_lines(body) == {uid(a): {"INR": 1000, "USD": 500}, uid(b): {"INR": -1000, "USD": -500}}
    assert sorted(tr(body)) == sorted([(uid(b), uid(a), 1000, "INR"), (uid(b), uid(a), 500, "USD")])
    # the same lines show up in the group list / detail
    for who, expect in ((a, {"INR": 1000, "USD": 500}), (b, {"INR": -1000, "USD": -500})):
        item = [g for g in client.get("/groups", headers=h(who)).json()["items"] if g["id"] == gid][0]
        assert lines(item["my_balances"]) == expect
        assert lines(client.get(f"/groups/{gid}", headers=h(who)).json()["my_balances"]) == expect


def test_group_list_and_detail_show_real_balances(client, flat):
    for who, expect in ((flat["a"], 6666), (flat["b"], -3333), (flat["c"], -3333)):
        item = [g for g in client.get("/groups", headers=h(who)).json()["items"] if g["id"] == flat["gid"]][0]
        assert lines(item["my_balances"]) == {"INR": expect}
        detail = client.get(f"/groups/{flat['gid']}", headers=h(who)).json()
        assert lines(detail["my_balances"]) == {"INR": expect}
        by_member = {m["user"]["id"]: lines(m["balances"]) for m in detail["members"]}
        assert by_member == {uid(flat["a"]): {"INR": 6666}, uid(flat["b"]): {"INR": -3333}, uid(flat["c"]): {"INR": -3333}}


def test_deleted_expense_is_ignored_and_vector_33_restore_gives_identical_balances(client, flat):
    a, b, gid = flat["a"], flat["b"], flat["gid"]
    e2 = create_group_expense(client, b, gid, equal_body(b, [a, b], total=500, description="Tea"))

    def snap():
        gb = group_balances(client, a, gid)
        friend = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
        return gb, friend["balances"], friend["breakdown"], client.get("/balances", headers=h(a)).json()

    before = snap()
    assert client.delete(f"/expenses/{flat['e']['id']}", headers=h(a)).status_code == 200
    mid = group_balances(client, a, gid)
    assert member_lines(mid) == {uid(a): {"INR": -250}, uid(b): {"INR": 250}, uid(flat["c"]): {}}
    assert snap() != before
    assert client.post(f"/expenses/{flat['e']['id']}/restore", headers=h(a)).status_code == 200
    assert snap() == before                                            # vector 33: identical snapshot
    assert e2["id"]


# ---- S4-B-2: friend balances, breakdown, settled_up_since, GET /balances -------------------------------------------

def test_friend_balance_non_group_only(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    nongroup_owes(client, a, b, 3000)
    fa = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
    assert lines(fa["balances"]) == {"INR": 3000}
    assert [(x["scope"], x["group_id"], x["group_name"], lines(x["balances"])) for x in fa["breakdown"]] == [
        ("non_group", None, None, {"INR": 3000})]
    assert fa["settled_up_since"] is None
    fb = client.get(f"/friends/{uid(a)}", headers=h(b)).json()
    assert lines(fb["balances"]) == {"INR": -3000}
    listed = {i["user"]["id"]: lines(i["balances"]) for i in client.get("/friends", headers=h(a)).json()["items"]}
    assert listed == {uid(b): {"INR": 3000}}


def test_friend_balance_sums_group_and_non_group_with_breakdown(client, flat):
    a, b, c = flat["a"], flat["b"], flat["c"]
    nongroup_owes(client, a, b, 1000)                                  # plus 3333 in Flat 4B
    fa = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
    assert lines(fa["balances"]) == {"INR": 4333}
    parts = {(x["scope"], x["group_id"]): (x["group_name"], lines(x["balances"])) for x in fa["breakdown"]}
    assert parts == {("non_group", None): (None, {"INR": 1000}), ("group", flat["gid"]): ("Flat 4B", {"INR": 3333})}
    assert lines(client.get(f"/friends/{uid(c)}", headers=h(a)).json()["balances"]) == {"INR": 3333}


def test_friend_balance_follows_the_simplify_edge_of_each_group(client, chain):
    """Business_rules 4.3: group part = the suggested edge between the pair (simplified or pairwise)."""
    a, b, c, gid = chain["a"], chain["b"], chain["c"], chain["gid"]
    on = {uid(f): lines(client.get(f"/friends/{uid(f)}", headers=h(a)).json()["balances"]) for f in (b, c)}
    assert on == {uid(b): {}, uid(c): {"INR": -1000}}                  # simplified edge A->C
    set_simplify(client, a, gid, False)
    off = {uid(f): lines(client.get(f"/friends/{uid(f)}", headers=h(a)).json()["balances"]) for f in (b, c)}
    assert off == {uid(b): {"INR": -1000}, uid(c): {}}                 # pairwise edge A->B
    ob = client.get("/balances", headers=h(b)).json()                  # B: owed 1000 by A, owes C 1000
    assert {x["user_id"]: lines(x["balances"]) for x in ob["by_friend"] if lines(x["balances"])} == {
        uid(a): {"INR": 1000}, uid(c): {"INR": -1000}}


def test_overall_balances_per_currency_never_summed(client):
    a, b, c, d = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev"))
    for u in (b, c, d):
        assert client.post("/friends", json={"email": f"{u['user']['name'].lower()}@example.com"}, headers=h(a)).status_code == 201
    nongroup_owes(client, a, b, 3000)                   # B owes A 3000 INR
    nongroup_owes(client, a, d, 2000)                   # D owes A 2000 INR
    nongroup_owes(client, c, a, 1000, who=a)            # A owes C 1000 INR
    nongroup_owes(client, c, a, 500, "USD", who=a)      # A owes C 500 USD
    r = client.get("/balances", headers=h(a))
    assert r.status_code == 200, f"GET /balances -> {r.status_code} (needs S4-B-2): {r.text}"
    body = r.json()
    assert lines(body["you_are_owed"]) == {"INR": 5000}
    assert lines(body["you_owe"]) == {"INR": 1000, "USD": 500}         # positive amounts, per currency
    assert {x["user_id"]: lines(x["balances"]) for x in body["by_friend"] if lines(x["balances"])} == {
        uid(b): {"INR": 3000}, uid(d): {"INR": 2000}, uid(c): {"INR": -1000, "USD": -500}}


def test_overall_balances_empty_for_new_user(client):
    a = user(client, "Asha")
    r = client.get("/balances", headers=h(a))
    assert r.status_code == 200, f"GET /balances -> {r.status_code} (needs S4-B-2)"
    assert r.json() == {"you_are_owed": [], "you_owe": [], "by_friend": []}


def test_settled_up_since_is_null_while_unsettled_and_set_when_every_balance_is_zero(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    f0 = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
    assert f0["settled_up_since"] is None and lines(f0["balances"]) == {}   # no activity yet
    nongroup_owes(client, a, b, 3000)
    f1 = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
    assert lines(f1["balances"]) == {"INR": 3000} and f1["settled_up_since"] is None
    back = nongroup_owes(client, b, a, 3000)                           # B pays A back through a mirror expense
    f2 = client.get(f"/friends/{uid(b)}", headers=h(a)).json()
    assert lines(f2["balances"]) == {} and f2["settled_up_since"] is not None, "settled_up_since is the zeroing event"
    since = datetime.fromisoformat(f2["settled_up_since"].replace("Z", "+00:00"))
    assert since >= datetime.fromisoformat(back["created_at"].replace("Z", "+00:00")).replace(microsecond=0)
    item = [i for i in client.get("/friends", headers=h(a)).json()["items"] if i["user"]["id"] == uid(b)][0]
    assert item["settled_up_since"] == f2["settled_up_since"]
    nongroup_owes(client, a, b, 100)                                   # unsettled again
    assert client.get(f"/friends/{uid(b)}", headers=h(a)).json()["settled_up_since"] is None


def test_group_summary_settled_up_since(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])

    def item():
        return [g for g in client.get("/groups", headers=h(a)).json()["items"] if g["id"] == gid][0]

    assert item()["settled_up_since"] is None                          # no activity
    owes(client, a, gid, b, 700)
    assert lines(item()["my_balances"]) == {"INR": 700} and item()["settled_up_since"] is None
    owes(client, b, gid, a, 700)
    assert lines(item()["my_balances"]) == {} and item()["settled_up_since"] is not None


# ---- S4-B-3 / vector 35: OUTSTANDING_BALANCE guard -----------------------------------------------------------------

def test_vector_35_leave_with_one_paisa_debt_is_409_with_balances(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    owes(client, a, gid, b, 1)                                         # B net -1 INR
    r = client.delete(f"/groups/{gid}/members/me", headers=h(b))
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "OUTSTANDING_BALANCE"
    assert r.json()["details"]["balances"] == [{"amount_minor": -1, "currency": "INR"}]
    members = client.get(f"/groups/{gid}", headers=h(a)).json()["members"]
    assert [m["left_at"] for m in members if m["user"]["id"] == uid(b)] == [None]   # still a member


def test_removal_by_another_member_is_also_blocked_and_a_creditor_is_blocked_too(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    owes(client, a, gid, b, 1)
    r = client.delete(f"/groups/{gid}/members/{uid(b)}", headers=h(a))
    assert r.status_code == 409 and r.json()["code"] == "OUTSTANDING_BALANCE"
    assert r.json()["details"]["balances"] == [{"amount_minor": -1, "currency": "INR"}]
    r = client.delete(f"/groups/{gid}/members/me", headers=h(a))            # +1 is non-zero as well
    assert r.status_code == 409 and r.json()["code"] == "OUTSTANDING_BALANCE"
    assert r.json()["details"]["balances"] == [{"amount_minor": 1, "currency": "INR"}]


def test_guard_lists_every_non_zero_currency_and_only_those(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    owes(client, a, gid, b, 250, "USD")
    owes(client, a, gid, b, 40, "INR")
    owes(client, b, gid, a, 40, "INR")                                 # INR back to 0
    r = client.delete(f"/groups/{gid}/members/me", headers=h(b))
    assert r.status_code == 409
    assert r.json()["details"]["balances"] == [{"amount_minor": -250, "currency": "USD"}]


def test_member_at_zero_in_every_currency_can_leave_204(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    owes(client, a, gid, b, 1)
    owes(client, a, gid, b, 300, "USD")
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 409
    owes(client, b, gid, a, 1)                                         # zero in INR, still -300 USD
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 409
    owes(client, b, gid, a, 300, "USD")                                # zero everywhere
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    members = client.get(f"/groups/{gid}", headers=h(a)).json()["members"]
    assert [m["left_at"] is not None for m in members if m["user"]["id"] == uid(b)] == [True]


def test_member_with_no_expenses_can_leave_and_removal_at_zero_is_204(client):
    a, b, c = (user(client, n) for n in ("Asha", "Ravi", "Meera"))
    gid = make_group(client, a, [b, c])
    assert client.delete(f"/groups/{gid}/members/{uid(c)}", headers=h(a)).status_code == 204


def test_a_deleted_expense_no_longer_blocks_leaving(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = owes(client, a, gid, b, 1)
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 409
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204


# ---- authorization --------------------------------------------------------------------------------------------------

def test_balances_require_auth_and_membership(client, flat):
    gid = flat["gid"]
    assert client.get(f"/groups/{gid}/balances").status_code == 401
    assert client.get("/balances").status_code == 401
    r = client.get(f"/groups/{gid}/balances", headers=h(flat["z"]))
    assert r.status_code == 403, f"non-member must get 403 (got {r.status_code}: {r.text})"
    assert r.json()["code"] == "FORBIDDEN"
    # a member who left may not read it either
    # (B owes nothing once A's expense is deleted)
    assert client.delete(f"/expenses/{flat['e']['id']}", headers=h(flat["a"])).status_code == 200
    assert client.delete(f"/groups/{gid}/members/me", headers=h(flat["b"])).status_code == 204
    assert client.get(f"/groups/{gid}/balances", headers=h(flat["b"])).status_code == 403


def test_outsider_balances_never_leak_into_other_users_overall_balances(client, flat):
    r = client.get("/balances", headers=h(flat["z"]))
    assert r.status_code == 200, f"GET /balances -> {r.status_code} (needs S4-B-2)"
    assert r.json() == {"you_are_owed": [], "you_owe": [], "by_friend": []}
    assert client.get(f"/friends/{uid(flat['a'])}", headers=h(flat["z"])).status_code == 404


# ---- settled_up_since after a member leaves (owner decision, QA E2E finding 1) ----------------------------------------
# Rule: for a friend whose balances are all zero, settled_up_since = the later of (the latest live expense created_at
# among shared scopes, including groups the viewer has left, and the time the viewer left the shared group); null only
# while non-zero or with no activity at all. The soft-deleted group contributes nothing.

def _ts(s):
    """ISO string -> naive UTC datetime (naive strings are taken as UTC)."""
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _friend(client, viewer, other):
    items = client.get("/friends", headers=h(viewer)).json()["items"]
    mine = [i for i in items if i["user"]["id"] == uid(other)]
    assert len(mine) == 1, "the friend must still be listed"
    single = client.get(f"/friends/{uid(other)}", headers=h(viewer)).json()
    assert single["settled_up_since"] == mine[0]["settled_up_since"]
    return mine[0]


def _left_at(client, viewer, gid, who):
    members = client.get(f"/groups/{gid}", headers=h(viewer)).json()["members"]
    v = [m["left_at"] for m in members if m["user"]["id"] == uid(who)]
    assert len(v) == 1 and v[0] is not None
    return _ts(v[0])


def test_viewer_leaves_after_offsetting_expenses_settled_up_since_is_last_expense_or_left_at(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    gid = make_group(client, a, [f])
    owes(client, f, gid, a, 1000)                                      # F pays 10.00 for A
    last = owes(client, a, gid, f, 1000)                               # A pays 10.00 for F -> zero
    assert client.delete(f"/groups/{gid}/members/me", headers=h(a)).status_code == 204
    left = _left_at(client, f, gid, a)
    item = _friend(client, a, f)
    assert lines(item["balances"]) == {}
    assert item["settled_up_since"] is not None, "viewer left: the relation is settled, not 'no activity'"
    assert _ts(item["settled_up_since"]) == max(_ts(last["created_at"]), left)


def test_left_at_later_than_last_expense_wins_and_later_expense_wins_over_left_at(client, db_session):
    a, f = user(client, "Asha"), user(client, "Farah")
    gid = make_group(client, a, [f])
    owes(client, f, gid, a, 500)
    last = owes(client, a, gid, f, 500)
    assert client.delete(f"/groups/{gid}/members/me", headers=h(a)).status_code == 204
    left = _left_at(client, f, gid, a)
    set_created_at(db_session, last["id"], (left - timedelta(days=5)).replace(tzinfo=timezone.utc))
    assert _friend(client, a, f)["settled_up_since"] is not None, "viewer left: relation settled, not null"
    assert _ts(_friend(client, a, f)["settled_up_since"]) == left          # left_at is the later one
    future = left + timedelta(days=5)
    set_created_at(db_session, last["id"], future.replace(tzinfo=timezone.utc))
    assert _ts(_friend(client, a, f)["settled_up_since"]) == future        # the expense is the later one


def test_viewer_left_but_other_group_with_friend_still_shared_uses_latest_across_scopes(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    g1, g2 = make_group(client, a, [f], name="One"), make_group(client, a, [f], name="Two")
    owes(client, f, g1, a, 700)
    owes(client, a, g1, f, 700)
    assert client.delete(f"/groups/{g1}/members/me", headers=h(a)).status_code == 204
    left = _left_at(client, f, g1, a)
    later = owes(client, a, g2, f, 100)                                # still shared group, unsettled
    assert _friend(client, a, f)["settled_up_since"] is None
    back = owes(client, f, g2, a, 100)                                 # zero again
    assert _ts(_friend(client, a, f)["settled_up_since"]) == max(_ts(back["created_at"]), left)


def test_friend_who_left_not_the_viewer_still_has_a_timestamp(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    gid = make_group(client, a, [f])
    owes(client, f, gid, a, 1000)
    last = owes(client, a, gid, f, 1000)
    assert client.delete(f"/groups/{gid}/members/me", headers=h(f)).status_code == 204
    item = _friend(client, a, f)
    assert lines(item["balances"]) == {}
    assert item["settled_up_since"] is not None
    assert _ts(item["settled_up_since"]) >= _ts(last["created_at"])


def test_non_zero_balance_after_viewer_would_leave_is_null_and_blocked(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    gid = make_group(client, a, [f])
    owes(client, f, gid, a, 1000)
    assert client.delete(f"/groups/{gid}/members/me", headers=h(a)).status_code == 409   # guard stays
    assert _friend(client, a, f)["settled_up_since"] is None
    assert client.delete(f"/groups/{gid}/members/me", headers=h(f)).status_code == 409
    assert _friend(client, a, f)["settled_up_since"] is None


def test_non_zero_balance_in_another_scope_keeps_null_even_after_leaving_a_settled_group(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    g1 = make_group(client, a, [f], name="One")
    owes(client, f, g1, a, 700)
    owes(client, a, g1, f, 700)
    assert client.delete(f"/groups/{g1}/members/me", headers=h(a)).status_code == 204
    nongroup_owes(client, f, a, 250)                                   # A owes F 2.50 outside any group
    item = _friend(client, a, f)
    assert lines(item["balances"]) == {"INR": -250} and item["settled_up_since"] is None


def test_no_activity_at_all_is_null_even_after_the_viewer_leaves(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    assert client.post("/friends", json={"email": "farah@example.com"}, headers=h(a)).status_code == 201
    assert _friend(client, a, f)["settled_up_since"] is None
    gid = make_group(client, a, [f])
    assert _friend(client, a, f)["settled_up_since"] is None
    assert client.delete(f"/groups/{gid}/members/me", headers=h(a)).status_code == 204
    item = _friend(client, a, f)
    assert lines(item["balances"]) == {} and item["settled_up_since"] is None


def test_soft_deleted_group_contributes_nothing_to_settled_up_since(client):
    a, f = user(client, "Asha"), user(client, "Farah")
    assert client.post("/friends", json={"email": "farah@example.com"}, headers=h(a)).status_code == 201
    gid = make_group(client, a, [f])
    owes(client, f, gid, a, 400)
    owes(client, a, gid, f, 400)
    assert _friend(client, a, f)["settled_up_since"] is not None       # the live group counts
    assert client.delete(f"/groups/{gid}", headers=h(a)).status_code in (200, 204)
    item = _friend(client, a, f)
    assert lines(item["balances"]) == {} and item["settled_up_since"] is None, "deleted group: no activity"
    earlier = nongroup_owes(client, a, f, 90)
    back = nongroup_owes(client, f, a, 90)
    assert _ts(_friend(client, a, f)["settled_up_since"]) == _ts(back["created_at"]), "only the live scope counts"
