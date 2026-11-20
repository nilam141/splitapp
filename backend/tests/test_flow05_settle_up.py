"""S5-Q-2 (API half): FLOW-05 steps 1-7 and its alternate paths, end to end through the HTTP API.
The emulator E2E half of S5-Q-2 is not covered here."""
from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user
from tests.settlement_helpers import befriend, pay, sbody
from tests.test_balances_api import group_balances, member_lines, tr


def nets(client, who, gid):
    return {u: v.get("INR", 0) for u, v in member_lines(group_balances(client, who, gid)).items()}


def test_flow_05_steps_1_to_7(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c])
    create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=10000))              # FLOW-03a
    A, B, C = uid(a), uid(b), uid(c)
    assert nets(client, c, gid) == {A: 6666, B: -3333, C: -3333}
    # 1. SCR-30 suggestion (simplify on): C -> A 3333
    body = group_balances(client, c, gid)
    assert body["simplified"] is True
    assert (C, A, 3333, "INR") in tr(body)
    # 2-3. partial payment of 20.00
    s1 = pay(client, c, c, a, 2000, group_id=gid)
    assert s1["amount"] == {"amount_minor": 2000, "currency": "INR"}
    # 4.
    assert nets(client, c, gid) == {A: 4666, B: -3333, C: -1333}
    assert (C, A, 1333, "INR") in tr(group_balances(client, c, gid))
    # 5. full: the prefilled remainder
    pay(client, c, c, a, 1333, group_id=gid)
    assert nets(client, c, gid) == {A: 3333, B: -3333, C: 0}
    # 6. C is settled in G: no C transfers, no balance lines, group list shows no balance for C
    assert not [t for t in tr(group_balances(client, c, gid)) if C in t[:2]]
    groups = client.get("/groups", headers=h(c)).json()["items"]
    mine = next(g for g in groups if g["id"] == gid)
    assert all(x["amount_minor"] == 0 for x in mine["my_balances"])
    # 7. settle all from the friend screen: 3333 in G and 500 non-group -> A-B total 0
    befriend(client, a, b)
    create_expense(client, a, {**equal_body(a, [a, b], total=1000), "group_id": None})      # B owes A 500 non-group
    r = client.post("/settlements/settle-all", json={"friend_user_id": uid(b)}, headers=h(a))
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    assert sorted(((s["group_id"], s["amount"]["amount_minor"]) for s in items), key=str) == \
        sorted([(gid, 3333), (None, 500)], key=str)
    assert {s["batch_id"] for s in items} == {r.json()["batch_id"]}
    assert nets(client, a, gid)[B] == 0
    assert [x for x in client.get(f"/friends/{B}", headers=h(a)).json()["balances"] if x["amount_minor"]] == []


def test_flow_05_alternate_paths(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c])
    create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=10000))
    A, C = uid(a), uid(c)
    pay(client, c, c, a, 2000, group_id=gid)                              # C owes 1333
    over = pay(client, c, c, a, 5000, group_id=gid)                       # overpay: A now owes C 3667
    assert nets(client, a, gid)[C] == 3667
    # overpay flips C from debtor to creditor: C 2000 + 5000 paid against 3333 owed -> C +3667, A 6666 - 7000 = -334
    assert nets(client, a, gid)[A] == -334
    assert {(f, t, x) for f, t, x, _ in tr(group_balances(client, a, gid))} == {(uid(b), C, 3333), (A, C, 334)}
    usd = pay(client, c, c, a, 500, "USD", group_id=gid)                  # other currency leaves INR alone
    assert member_lines(group_balances(client, a, gid))[C]["INR"] == 3667
    assert member_lines(group_balances(client, a, gid))[C]["USD"] == 500
    # delete reverts, restore re-applies
    assert client.delete(f"/settlements/{over['id']}", headers=h(c)).status_code == 200
    assert nets(client, a, gid)[C] == -1333
    assert client.post(f"/settlements/{over['id']}/restore", headers=h(c)).status_code == 200
    assert nets(client, a, gid)[C] == 3667
    r = client.post("/settlements", json=sbody(c, c, 100, group_id=gid), headers=h(c))
    assert r.status_code == 422 and r.json()["code"] == "SAME_PARTY"
    assert usd["amount"]["currency"] == "USD"
