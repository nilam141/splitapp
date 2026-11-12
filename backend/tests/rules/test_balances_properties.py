"""S4-Q-2: property tests for business_rules vector 40 (Hypothesis, 2,000 random group histories per run).

A history is 2-12 members, 0-50 expenses (random payers, owed amounts, currencies, amounts up to 9,999,999,999)
and 0-30 settlements (random pair, any amount, so overpayments occur), in the shape documented in
tests/rules/balances_shim.py. Hypothesis draws the sizes and a seed; the records are built by a seeded
random.Random, which keeps 2,000 examples fast while sizes still shrink. Integer minor units only.

Properties: sum of nets = 0 per currency; simplify() zeroes every net and uses <= (non-zero members - 1) transfers
and equals the business_rules section 5 reference loop; pairwise edges net to the same per-user nets and are
canonical-ordered; nets do not depend on record order.

NOT tested, on purpose: "simplified list is never longer than the pairwise list". It is false for the greedy
algorithm (Hypothesis finds histories with settlements where simplify() gives 5 transfers and the pairwise list 4);
see the QA handoff in docs/progress.md.
Written before app.balances exists: fails with NotImplementedError.
"""
import random

from hypothesis import HealthCheck, given, note, settings, strategies as st

from tests.rules.balances_shim import balances, expense, settlement

EXAMPLES = 2000
CFG = settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck), database=None)
MAX_T = 9_999_999_999
CURRENCIES = ["INR", "USD", "JPY"]


def partition(rng, total, parts, minimum=0):
    """`parts` integers >= minimum that sum to `total` (requires total >= parts * minimum)."""
    rest = total - parts * minimum
    cuts = sorted(rng.randint(0, rest) for _ in range(parts - 1))
    edges = [0] + cuts + [rest]
    return [minimum + edges[i + 1] - edges[i] for i in range(parts)]


def build_history(seed, n_members, n_expenses, n_settlements):
    rng = random.Random(seed)
    users = [chr(ord("A") + i) for i in range(n_members)]
    expenses, settlements = [], []
    for _ in range(n_expenses):
        total = rng.choice([rng.randint(1, 100), rng.randint(1, 1_000_000), rng.randint(1, MAX_T)])
        k = rng.randint(1, min(n_members, total))
        payers = rng.sample(users, k)
        paid = partition(rng, total, k, minimum=1)
        owers = rng.sample(users, rng.randint(1, n_members))
        owed = partition(rng, total, len(owers))
        expenses.append(expense(rng.choice(CURRENCIES), list(zip(payers, paid)), list(zip(owers, owed))))
    for _ in range(n_settlements):
        a, b = rng.sample(users, 2)
        settlements.append(settlement(rng.choice(CURRENCIES), a, b, rng.choice([rng.randint(1, 5000), rng.randint(1, MAX_T)])))
    return users, expenses, settlements


histories = st.builds(
    build_history,
    seed=st.integers(0, 2**63 - 1),
    n_members=st.integers(2, 12),
    n_expenses=st.integers(0, 50),
    n_settlements=st.integers(0, 30),
)


def reference_simplify(nets, canonical):
    """business_rules section 5, verbatim."""
    b = dict(nets)
    out = []
    while any(v > 0 for v in b.values()):
        c = max((u for u in canonical if b.get(u, 0) > 0), key=lambda u: (b[u], -canonical.index(u)))
        d = max((u for u in canonical if b.get(u, 0) < 0), key=lambda u: (-b[u], -canonical.index(u)))
        x = min(b[c], -b[d])
        out.append((d, c, x))
        b[c] -= x
        b[d] += x
    return out


def apply(nets, transfers):
    b = {u: nets.get(u, 0) for u in nets}
    for frm, to, amount in transfers:
        b[frm] = b.get(frm, 0) + amount   # paying reduces what you owe
        b[to] = b.get(to, 0) - amount
    return b


@CFG
@given(history=histories)
def test_nets_sum_to_zero_per_currency(history):
    users, expenses, settlements = history
    nets = balances().net_balances(expenses, settlements)
    used = {e["currency"] for e in expenses} | {s["currency"] for s in settlements}
    assert set(nets) >= {c for c in used if any(v for v in nets.get(c, {}).values())}
    for cur, by_user in nets.items():
        assert sum(by_user.values()) == 0, cur
        assert set(by_user) <= set(users)
        assert all(type(v) is int for v in by_user.values())


@CFG
@given(history=histories)
def test_simplify_settles_everything_with_at_most_n_minus_1_transfers(history):
    users, expenses, settlements = history
    b = balances()
    for cur, nets in b.net_balances(expenses, settlements).items():
        transfers = [tuple(t) for t in b.simplify(nets, users)]
        note(f"{cur}: nets={nets} transfers={transfers}")
        after = apply(nets, transfers)
        assert all(v == 0 for v in after.values()), "simplify() must zero every net"
        non_zero = sum(1 for v in nets.values() if v != 0)
        assert len(transfers) <= max(non_zero - 1, 0)
        for frm, to, amount in transfers:
            assert type(amount) is int and amount >= 1 and frm != to
            assert nets.get(frm, 0) < 0 < nets.get(to, 0), "debtor pays creditor"
        assert transfers == reference_simplify(nets, users)  # same order and tie-breaks as section 5


@CFG
@given(history=histories)
def test_pairwise_edges_net_to_the_same_nets(history):
    users, expenses, settlements = history
    b = balances()
    nets = b.net_balances(expenses, settlements)
    edges = b.pairwise_edges(expenses, settlements, canonical=users)
    for cur in set(nets) | set(edges):
        listed = [tuple(e) for e in edges.get(cur, [])]
        implied = {u: 0 for u in users}
        for frm, to, amount in listed:               # frm owes to
            assert type(amount) is int and amount >= 1 and frm != to
            implied[frm] -= amount
            implied[to] += amount
        expected = {u: nets.get(cur, {}).get(u, 0) for u in users}
        assert implied == expected, cur
        pairs = {(f, t) for f, t, _ in listed}
        assert len(pairs) == len(listed), "one edge per ordered pair"
        assert not any((t, f) in pairs for f, t in pairs), "unordered pairs are netted"
        order = [(users.index(f), users.index(t)) for f, t, _ in listed]
        assert order == sorted(order), "debtor then creditor, canonical order"


@CFG
@given(history=histories, shuffle_seed=st.integers(0, 2**32))
def test_nets_do_not_depend_on_record_order(history, shuffle_seed):
    users, expenses, settlements = history
    rng = random.Random(shuffle_seed)
    e2, s2 = list(expenses), list(settlements)
    rng.shuffle(e2)
    rng.shuffle(s2)

    def clean(nets):
        return {c: {u: v for u, v in m.items() if v} for c, m in nets.items() if any(m.values())}

    b = balances()
    assert clean(b.net_balances(e2, s2)) == clean(b.net_balances(expenses, settlements))


@CFG
@given(history=histories)
def test_pairwise_edges_per_expense_give_exact_creditor_and_debtor_totals(history):
    """S4-Q-4 (section 4.2, OQ-44): for ONE expense, every debtor's outgoing edges sum to exactly |net| and every
    creditor's incoming edges sum to exactly its net (debtors and creditors are disjoint, so no netting is involved)."""
    users, expenses, _ = history
    b = balances()
    for e in expenses:
        cur = e["currency"]
        nets = {}
        for u, paid in e["payers"]:
            nets[u] = nets.get(u, 0) + paid
        for u, owed in e["splits"]:
            nets[u] = nets.get(u, 0) - owed
        out, inc = {}, {}
        for frm, to, amount in b.pairwise_edges([e], canonical=users).get(cur, []):
            assert type(amount) is int and amount >= 1
            out[frm] = out.get(frm, 0) + amount
            inc[to] = inc.get(to, 0) + amount
        for u in users:
            n = nets.get(u, 0)
            assert out.get(u, 0) == max(0, -n), f"debtor {u}"
            assert inc.get(u, 0) == max(0, n), f"creditor {u}"
