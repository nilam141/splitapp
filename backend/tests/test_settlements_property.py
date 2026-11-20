"""S5-B-1 definition of done, API level: random settlements (create, edit, delete, restore) mixed with random expenses
feed `GET /groups/{id}/balances`. Complements the pure-function properties in tests/rules (S4-Q-2), which already draw
random settlements; this one proves the DB balance query includes settlement rows.

Per example: a fresh group of 2-4 members, 1-8 random operations, then
  * the per-member balances equal the nets computed here from the live records (integers, business_rules section 4)
  * the nets sum to 0 per currency
  * applying the returned transfers to the nets zeroes every one (simplified list and pairwise list)
Fails before S5-B-2 at the first POST /settlements (404), reported with "needs S5-B-2".
"""
import random

from hypothesis import HealthCheck, given, settings, strategies as st

from tests.expense_helpers import create_group_expense, h, make_group, uid, user
from tests.settlement_helpers import pay
from tests.test_balances_api import exact_body, group_balances, member_lines, set_simplify

CURRENCIES = ["INR", "USD", "JPY"]
CFG = settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck), database=None)


def run_history(client, people, seed, n_members, n_ops, simplified):
    rng = random.Random(seed)
    members = people[:n_members]
    gid = make_group(client, members[0], members[1:])
    set_simplify(client, members[0], gid, simplified)
    nets = {}                                   # (user_id, currency) -> int
    live = {}                                   # settlement id -> (frm, to, amount, currency, deleted)

    def bump(u, cur, d):
        nets[(u, cur)] = nets.get((u, cur), 0) + d

    for _ in range(n_ops):
        kind = rng.choice(["expense", "expense", "settle", "settle", "delete", "restore", "edit"])
        cur = rng.choice(CURRENCIES)
        if kind == "expense":
            payer = rng.choice(members)
            owers = rng.sample(members, rng.randint(1, n_members))
            debts = [(o, rng.randint(1, 100_000)) for o in owers]
            total = sum(v for _, v in debts)
            create_group_expense(client, payer, gid, exact_body(payer, debts, cur, total))
            bump(uid(payer), cur, total)
            for o, v in debts:
                bump(uid(o), cur, -v)
        elif kind == "settle":
            frm, to = rng.sample(members, 2)
            amt = rng.choice([rng.randint(1, 5000), rng.randint(1, 9_999_999_999)])
            s = pay(client, rng.choice(members), frm, to, amt, cur, group_id=gid)
            live[s["id"]] = [uid(frm), uid(to), amt, cur, False, s["version"]]
            bump(uid(frm), cur, amt)
            bump(uid(to), cur, -amt)
        elif live:
            sid = rng.choice(sorted(live))
            frm, to, amt, scur, deleted, version = live[sid]
            sign = 0
            if kind == "delete" and not deleted:
                r = client.delete(f"/settlements/{sid}", headers=h(members[0]))
                assert r.status_code == 200, r.text
                sign, live[sid][4], live[sid][5] = -1, True, r.json()["version"]     # delete bumps the version
            elif kind == "restore" and deleted:
                r = client.post(f"/settlements/{sid}/restore", headers=h(members[0]))
                assert r.status_code == 200, r.text
                sign, live[sid][4], live[sid][5] = 1, False, r.json()["version"]     # so does restore
            elif kind == "edit" and not deleted:
                new = rng.randint(1, 20_000)
                r = client.patch(f"/settlements/{sid}", json={"version": version,
                                 "amount": {"amount_minor": new, "currency": scur}}, headers=h(members[0]))
                assert r.status_code == 200, r.text
                bump(frm, scur, new - amt)
                bump(to, scur, amt - new)
                live[sid][2], live[sid][5] = new, r.json()["version"]
            if sign:
                bump(frm, scur, sign * amt)
                bump(to, scur, -sign * amt)

    body = group_balances(client, members[0], gid)
    got = member_lines(body)
    for m in members:
        for cur in CURRENCIES:
            assert got[uid(m)].get(cur, 0) == nets.get((uid(m), cur), 0), (uid(m), cur)
    for cur in CURRENCIES:
        assert sum(got[uid(m)].get(cur, 0) for m in members) == 0
    after = dict(nets)
    for t in body["transfers"]:
        assert type(t["amount_minor"]) is int and t["amount_minor"] > 0
        after[(t["from_user_id"], t["currency"])] = after.get((t["from_user_id"], t["currency"]), 0) + t["amount_minor"]
        after[(t["to_user_id"], t["currency"])] = after.get((t["to_user_id"], t["currency"]), 0) - t["amount_minor"]
    assert all(v == 0 for v in after.values()), "applying the transfers must settle every balance"


def test_random_expenses_and_settlements_keep_group_balances_exact(client):
    people = [user(client, n) for n in ("Asha", "Ravi", "Meera", "Kiran")]

    @CFG
    @given(seed=st.integers(0, 2**63 - 1), n_members=st.integers(2, 4), n_ops=st.integers(1, 8),
           simplified=st.booleans())
    def prop(seed, n_members, n_ops, simplified):
        run_history(client, people, seed, n_members, n_ops, simplified)

    prop()
