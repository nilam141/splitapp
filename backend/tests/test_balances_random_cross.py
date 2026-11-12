"""S4-Q-3 (balances half): 50 seeded random groups; GET /groups/{id}/balances must equal the pure functions in
app.balances applied to the live expenses the API returned when they were created.

Expected values come from the pure functions (net_balances, suggested_transfers), fed with the payers/splits of the
POST responses (not from the balances service), with some expenses soft-deleted and restored along the way, random
simplify on/off, 2-6 members, 1-3 currencies (INR, USD, JPY, incl. a 0-decimal one), equal/exact/percent/shares splits and
multi-payer expenses. Also asserted: members in creation (canonical) order, transfers ordered by currency code and
positive, every transfer settles to net zero, and the member nets sum to zero per currency.
"""
import random

import pytest

from app.balances import net_balances, suggested_transfers
from tests.expense_helpers import create_group_expense, h, make_group, uid, user

SEED = 20261110
N_GROUPS = 50
CURRENCIES = ["INR", "USD", "JPY"]


def _body(rng, creator, members, currency):
    total = rng.choice([rng.randint(1, 100), rng.randint(100, 100000), rng.randint(100000, 5_000_000)])
    k = rng.randint(1, len(members))
    parts = rng.sample(members, k)
    if creator not in parts and rng.random() < 0.7:
        parts.append(creator)
    kind = rng.choice(["equal", "exact", "percent", "shares"])
    if kind == "equal":
        split = {"type": "equal", "entries": [{"user_id": uid(p)} for p in parts]}
    elif kind == "exact":
        cuts = sorted(rng.randint(0, total) for _ in range(len(parts) - 1))
        vals = [b - a for a, b in zip([0] + cuts, cuts + [total])]
        split = {"type": "exact", "entries": [{"user_id": uid(p), "value": v} for p, v in zip(parts, vals)]}
    elif kind == "percent":
        cuts = sorted(rng.randint(0, 10000) for _ in range(len(parts) - 1))
        vals = [b - a for a, b in zip([0] + cuts, cuts + [10000])]
        split = {"type": "percent", "entries": [{"user_id": uid(p), "value": v} for p, v in zip(parts, vals)]}
    else:
        split = {"type": "shares", "entries": [{"user_id": uid(p), "value": rng.randint(1, 9)} for p in parts]}
    npay = rng.randint(1, min(3, len(members)))
    payers = rng.sample(members, npay)
    if creator not in payers and creator not in parts:
        payers[0] = creator
    cuts = sorted(rng.randint(0, total) for _ in range(npay - 1))
    paid = [b - a for a, b in zip([0] + cuts, cuts + [total])]
    return {"description": "x", "total": {"amount_minor": total, "currency": currency}, "expense_date": "2026-11-05",
            "payers": [{"user_id": uid(p), "paid_amount_minor": v} for p, v in zip(payers, paid) if v > 0] or
                      [{"user_id": uid(payers[0]), "paid_amount_minor": total}],
            "split": split}


def _record(e):
    return {"currency": e["total"]["currency"],
            "payers": [(p["user_id"], p["paid_amount_minor"]) for p in e["payers"]],
            "splits": [(s["user_id"], s["owed_amount_minor"]) for s in e["splits"]]}


@pytest.mark.parametrize("batch", range(5))
def test_group_balances_equal_the_pure_functions_for_random_groups(client, batch):
    rng = random.Random(SEED + batch)
    checked_transfers = 0
    multi_payer = off_groups = friend_checks = 0
    for gi in range(N_GROUPS // 5):
        tag = f"{batch}{gi}"
        people = [user(client, f"P{tag}x{i}") for i in range(rng.randint(2, 6))]
        creator, others = people[0], people[1:]
        gid = make_group(client, creator, others, f"G{tag}")
        canonical = [uid(p) for p in people]
        currencies = rng.sample(CURRENCIES, rng.randint(1, 3))
        live = []
        for _ in range(rng.randint(1, 12)):
            body = _body(rng, creator, people, rng.choice(currencies))
            r = client.post(f"/groups/{gid}/expenses", json=body, headers=h(creator))
            assert r.status_code == 201, (body, r.text)
            e = r.json()
            multi_payer += len(e["payers"]) > 1
            if rng.random() < 0.2:  # soft-delete, and sometimes restore
                assert client.delete(f"/expenses/{e['id']}", headers=h(creator)).status_code == 200
                if rng.random() < 0.4:
                    assert client.post(f"/expenses/{e['id']}/restore", headers=h(creator)).status_code == 200
                    live.append(e)
            else:
                live.append(e)
        simplified = rng.random() < 0.6
        v = client.get(f"/groups/{gid}", headers=h(creator)).json()["version"]
        assert client.patch(f"/groups/{gid}", json={"version": v, "simplify_debts": simplified},
                            headers=h(creator)).status_code == 200

        records = [_record(e) for e in live]
        nets = net_balances(records)
        expected_transfers = suggested_transfers(records, [], canonical, simplified)

        member = people[rng.randrange(len(people))]  # any member sees the same group balances
        r = client.get(f"/groups/{gid}/balances", headers=h(member))
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["simplified"] is simplified and got["group_id"] == gid
        assert [m["user_id"] for m in got["members"]] == canonical

        for m in got["members"]:
            api = {x["currency"]: x["amount_minor"] for x in m["balances"] if x["amount_minor"] != 0}
            want = {c: n[m["user_id"]] for c, n in nets.items() if n.get(m["user_id"], 0) != 0}
            assert api == want, (gid, m["user_id"])
        for c, n in nets.items():
            assert sum(n.values()) == 0
        want_t = [(f, t, a, c) for c in sorted(expected_transfers) for f, t, a in expected_transfers[c]]
        got_t = [(t["from_user_id"], t["to_user_id"], t["amount_minor"], t["currency"]) for t in got["transfers"]]
        assert got_t == want_t, (gid, simplified)
        assert all(a >= 1 for _, _, a, _ in got_t)
        checked_transfers += len(got_t)
        if not simplified:  # 4.2 controlled rounding: the pairwise list is exact for every member (S4-B-4)
            off_groups += 1
            for m in got["members"]:
                for c, n in nets.items():
                    per_c = sum((a if t == m["user_id"] else -a if f == m["user_id"] else 0)
                                for f, t, a, cur in got_t if cur == c)
                    assert per_c == n.get(m["user_id"], 0), (gid, c, m["user_id"], per_c, n.get(m["user_id"]))
        # Friend view (4.3): with no non-group expenses, my balance with a co-member is the signed suggested edge of
        # this group (simplified or pairwise by the toggle), per currency, and the breakdown is that one group scope.
        me = uid(member)
        for other in canonical:
            if other == me:
                continue
            want_f: dict[str, int] = {}
            for f, t, a, c in got_t:
                if t == me and f == other:
                    want_f[c] = want_f.get(c, 0) + a
                elif f == me and t == other:
                    want_f[c] = want_f.get(c, 0) - a
            fr = client.get(f"/friends/{other}", headers=h(member))
            assert fr.status_code == 200, fr.text
            fb = fr.json()
            assert {x["currency"]: x["amount_minor"] for x in fb["balances"]} == want_f, (gid, simplified, other)
            assert [(x["scope"], x["group_id"]) for x in fb["breakdown"]] == ([("group", gid)] if want_f else [])
            for x in fb["breakdown"]:
                assert {y["currency"]: y["amount_minor"] for y in x["balances"]} == want_f
            friend_checks += 1
        if simplified:  # applying the transfers settles every net to zero
            for c in nets:
                left = dict(nets[c])
                for f, t, a, cur in got_t:
                    if cur == c:
                        left[f] = left.get(f, 0) + a
                        left[t] = left.get(t, 0) - a
                assert all(x == 0 for x in left.values()), (gid, c, left)
    assert multi_payer > 0, "generator produced no multi-payer expense"
    assert friend_checks > 0
    assert checked_transfers > 0, "generator produced no transfers at all"
