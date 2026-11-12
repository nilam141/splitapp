"""S4-Q-1: business_rules vectors 17, 19-24, 28, 33 against the pure functions in app.balances (S4-B-1).

Signatures are documented in tests/rules/balances_shim.py and docs/progress.md. Written before the module exists:
every test fails with NotImplementedError("module app.balances does not exist yet (S4-B-1)").
Vectors 19-24 compare ORDERED lists (order is part of the contract). Integer minor units only.
"""
import pytest

from tests.rules.balances_shim import balances, expense, settlement

CANON = ["A", "B", "C", "D"]
INR = "INR"

# ---- fixtures expressed as expense records -----------------------------------------------------------------------
V17 = [expense(INR, [("A", 6000), ("B", 3000)], [("A", 3000), ("B", 3000), ("C", 3000)])]
# A owes B 1000 (B paid for A), B owes C 1000 (C paid for B): nets A -1000, B 0, C +1000
CHAIN = [expense(INR, [("B", 1000)], [("A", 1000)]), expense(INR, [("C", 1000)], [("B", 1000)])]
# T 10000, A paid 7000, B 3000, equal over A, B, C, D (2500 each): nets A +4500, B +500, C -2500, D -2500
V23 = [expense(INR, [("A", 7000), ("B", 3000)], [(u, 2500) for u in "ABCD"])]
# nets A +3334, B +3333, C -3333, D -3334 (A, B paid; C, D owe)
V24 = [expense(INR, [("A", 3334), ("B", 3333)], [("C", 3333), ("D", 3334)])]


def nonzero(nets):
    return {u: v for u, v in nets.items() if v != 0}


def tr(*rows):
    return [tuple(r) for r in rows]


# ---- net_balances: vectors 17, 19, 22 (nets from expenses), 23, 24, 28 -------------------------------------------

@pytest.mark.parametrize("vector, expenses, expected", [
    ("17", V17, {"A": 3000, "B": 0, "C": -3000}),
    ("19", CHAIN, {"A": -1000, "B": 0, "C": 1000}),
    ("22/23", V23, {"A": 4500, "B": 500, "C": -2500, "D": -2500}),
    ("24", V24, {"A": 3334, "B": 3333, "C": -3333, "D": -3334}),
], ids=["v17", "v19", "v22-v23", "v24"])
def test_net_balances_vectors(vector, expenses, expected):
    nets = balances().net_balances(expenses)
    assert set(nets) == {INR}
    got = nets[INR]
    assert {u: got.get(u, 0) for u in expected} == expected
    assert set(got) - set(expected) == set()
    assert sum(got.values()) == 0
    assert all(type(v) is int for v in got.values())


def test_vector_5_payer_not_in_split_nets():
    nets = balances().net_balances([expense(INR, [("A", 9000)], [("B", 4500), ("C", 4500)])])[INR]
    assert {u: nets.get(u, 0) for u in "ABC"} == {"A": 9000, "B": -4500, "C": -4500}


# ---- simplify: vectors 19, 20, 22 (ordered transfers) --------------------------------------------------------------

@pytest.mark.parametrize("vector, nets, canonical, expected", [
    ("19", {"A": -1000, "B": 0, "C": 1000}, ["A", "B", "C"], tr(("A", "C", 1000))),
    ("20", {"A": -3000, "B": -1000, "C": 2500, "D": 1500}, CANON,
     tr(("A", "C", 2500), ("B", "D", 1000), ("A", "D", 500))),
    ("22", {"A": 4500, "B": 500, "C": -2500, "D": -2500}, CANON,
     tr(("C", "A", 2500), ("D", "A", 2000), ("D", "B", 500))),
], ids=["v19", "v20", "v22"])
def test_simplify_vectors(vector, nets, canonical, expected):
    got = balances().simplify(nets, canonical)
    assert [tuple(t) for t in got] == expected
    assert all(type(t[2]) is int for t in got)


def test_vector_22_end_to_end_from_expenses():
    nets = balances().net_balances(V23)[INR]
    assert [tuple(t) for t in balances().simplify(nets, CANON)] == tr(("C", "A", 2500), ("D", "A", 2000), ("D", "B", 500))


def test_vector_20_does_not_mutate_input_and_is_repeatable():
    nets = {"A": -3000, "B": -1000, "C": 2500, "D": 1500}
    keep = dict(nets)
    first = balances().simplify(nets, CANON)
    assert nets == keep
    assert balances().simplify(nets, CANON) == first


def test_simplify_all_zero_is_empty():
    assert balances().simplify({"A": 0, "B": 0}, ["A", "B"]) == []
    assert balances().simplify({}, []) == []


def test_simplify_tie_goes_to_earlier_canonical_member():
    # two equal debtors (C, D) and one creditor: C is earlier, so C pays first (vector 22 shape)
    got = balances().simplify({"A": 400, "B": 0, "C": -200, "D": -200}, CANON)
    assert [tuple(t) for t in got] == tr(("C", "A", 200), ("D", "A", 200))
    # same data, canonical order reversed: D is earlier now
    got = balances().simplify({"A": 400, "B": 0, "C": -200, "D": -200}, list(reversed(CANON)))
    assert [tuple(t) for t in got] == tr(("D", "A", 200), ("C", "A", 200))


# ---- pairwise_edges: vectors 21, 23, 24 --------------------------------------------------------------------------

def test_vector_21_pairwise_chain_simplify_off():
    edges = balances().pairwise_edges(CHAIN, canonical=["A", "B", "C"])
    assert [tuple(t) for t in edges[INR]] == tr(("A", "B", 1000), ("B", "C", 1000))


def test_vector_23_pairwise_multiple_payers():
    edges = balances().pairwise_edges(V23, canonical=CANON)
    assert [tuple(t) for t in edges[INR]] == tr(("C", "A", 2250), ("C", "B", 250), ("D", "A", 2250), ("D", "B", 250))


def test_vector_24_pairwise_uneven_credit():
    edges = balances().pairwise_edges(V24, canonical=CANON)
    assert [tuple(t) for t in edges[INR]] == tr(("C", "A", 1667), ("C", "B", 1666), ("D", "A", 1667), ("D", "B", 1667))


def test_pairwise_nets_opposite_directions_between_one_pair():
    # A paid 1000 for B, then B paid 400 for A: only B -> A 600 remains
    ex = [expense(INR, [("A", 1000)], [("B", 1000)]), expense(INR, [("B", 400)], [("A", 400)])]
    edges = balances().pairwise_edges(ex, canonical=["A", "B"])
    assert [tuple(t) for t in edges[INR]] == tr(("B", "A", 600))


def test_pairwise_exact_cancel_leaves_no_edge():
    ex = [expense(INR, [("A", 1000)], [("B", 1000)]), expense(INR, [("B", 1000)], [("A", 1000)])]
    edges = balances().pairwise_edges(ex, canonical=["A", "B"])
    assert edges.get(INR, []) == []


# ---- settlement records (input shape shared with the S4-Q-2 generator; vectors 25-27 are S5-Q-1) ---------------------

@pytest.mark.parametrize("paid", [2000, 5000], ids=["partial-v25-shape", "full-v26-shape"])
def test_settlement_reduces_debt_in_nets_and_edges(paid):
    owes = [expense(INR, [("A", 5000)], [("B", 5000)])]
    st = [settlement(INR, "B", "A", paid)]
    nets = balances().net_balances(owes, st)[INR]
    assert (nets.get("A", 0), nets.get("B", 0)) == (5000 - paid, paid - 5000)
    edges = balances().pairwise_edges(owes, st, canonical=["A", "B"]).get(INR, [])
    assert [tuple(t) for t in edges] == ([("B", "A", 5000 - paid)] if paid < 5000 else [])


def test_vector_27_overpayment_flips_direction():
    owes = [expense(INR, [("A", 3000)], [("B", 3000)])]
    st = [settlement(INR, "B", "A", 5000)]
    nets = balances().net_balances(owes, st)[INR]
    assert (nets.get("A", 0), nets.get("B", 0)) == (-2000, 2000)
    assert [tuple(t) for t in balances().pairwise_edges(owes, st, canonical=["A", "B"])[INR]] == tr(("A", "B", 2000))
    assert [tuple(t) for t in balances().simplify(nets, ["A", "B"])] == tr(("A", "B", 2000))


def test_settlement_in_other_currency_leaves_the_inr_debt():
    owes = [expense(INR, [("A", 3000)], [("B", 3000)])]
    nets = balances().net_balances(owes, [settlement("USD", "B", "A", 3000)])
    assert (nets[INR].get("A", 0), nets[INR].get("B", 0)) == (3000, -3000)
    assert (nets["USD"].get("A", 0), nets["USD"].get("B", 0)) == (-3000, 3000)


# ---- vector 28: currencies kept apart -----------------------------------------------------------------------------

def test_vector_28_multi_currency_kept_apart():
    ex = [expense("INR", [("A", 1000)], [("B", 1000)]),                       # B owes A 1000 INR
          expense("USD", [("A", 1000)], [("A", 500), ("B", 500)])]            # 1000 cents, A paid, equal A, B
    b = balances()
    nets = b.net_balances(ex)
    assert set(nets) == {"INR", "USD"}
    assert {u: nets["INR"].get(u, 0) for u in "AB"} == {"A": 1000, "B": -1000}
    assert {u: nets["USD"].get(u, 0) for u in "AB"} == {"A": 500, "B": -500}
    edges = b.pairwise_edges(ex, canonical=["A", "B"])
    assert [tuple(t) for t in edges["INR"]] == tr(("B", "A", 1000))
    assert [tuple(t) for t in edges["USD"]] == tr(("B", "A", 500))
    assert [tuple(t) for t in b.simplify(nets["INR"], ["A", "B"])] == tr(("B", "A", 1000))
    assert [tuple(t) for t in b.simplify(nets["USD"], ["A", "B"])] == tr(("B", "A", 500))


# ---- vector 33: delete then restore gives identical balances ------------------------------------------------------

def test_vector_33_delete_and_restore_snapshot_compare():
    """The pure functions only see live records: delete = drop E from the input, restore = put it back."""
    e1 = expense(INR, [("A", 6000)], [(u, 2000) for u in "ABC"])
    e2 = expense(INR, [("B", 3000)], [("A", 1000), ("B", 1000), ("C", 1000)])
    live = [e1, e2]
    b = balances()

    def snapshot(ex):
        n = b.net_balances(ex)
        p = b.pairwise_edges(ex, canonical=["A", "B", "C"])
        return (
            {c: nonzero(v) for c, v in n.items() if nonzero(v)},
            {c: [tuple(t) for t in v] for c, v in p.items() if v},
            {c: [tuple(t) for t in b.simplify(v, ["A", "B", "C"])] for c, v in n.items() if nonzero(v)},
        )

    before = snapshot(live)
    deleted = snapshot([e2])            # e1 deleted
    assert deleted != before
    restored = snapshot([e1, e2])       # e1 restored
    assert restored == before
    assert snapshot(list(reversed(live))) == before  # input order does not matter


# ---- section 4.2 rounding gap (found by the S4-Q-2 property test; reported to the Architect) --------------------------

def test_pairwise_edges_give_every_creditor_exactly_its_net_single_expense():
    """A, B, C each paid 1; D owes 1, E owes 2 (nets +1, +1, +1, -1, -2). The literal 4.2 rule spreads D's 1 over
    A:B:C = 1:1:1 and E's 2 over the same weights with split_weighted (ties by canonical order): D->A 1, E->A 1,
    E->B 1, so A receives 2 and C receives 0 although C's net is +1. Edges must net to the nets (S4-Q-2), so this
    needs either a different allocation in 4.2 or a documented tolerance; the Architect decides."""
    ex = [expense(INR, [("A", 1), ("B", 1), ("C", 1)], [("D", 1), ("E", 2)])]
    edges = balances().pairwise_edges(ex, canonical=list("ABCDE"))[INR]
    received = {u: 0 for u in "ABCDE"}
    for frm, to, amount in edges:
        received[to] += amount
        received[frm] -= amount
    assert received == {"A": 1, "B": 1, "C": 1, "D": -1, "E": -2}


# ---- S4-Q-4: section 4.2 controlled rounding (decided 2026-11-11, OQ-44): vectors 23, 24, 61 --------------------------
# Hand check of vector 24 (S = 6667): C->A p = 3333*3334 = 11112222 = 1666*6667 + 5000; C->B p = 11108889 = 1666*6667 +
# 1667; D->A p = 11115556 = 1667*6667 + 1667; D->B p = 11112222 -> 1666 r 5000. R[C] = 3333 - 3332 = 1, R[D] = 3334 -
# 3333 = 1, K[A] = 3334 - 3333 = 1, K[B] = 3333 - 3332 = 1. Walk: r 5000 cells first, debtor order: C->A (accept), D->B
# (accept); the r 1667 cells are then unneeded. Result C->A 1667, C->B 1666, D->A 1667, D->B 1667.
V61 = [expense(INR, [("A", 1), ("B", 1), ("C", 1)], [("D", 1), ("E", 2)])]


def totals_per_user(edges):
    out, inc = {}, {}
    for frm, to, amount in edges:
        out[frm] = out.get(frm, 0) + amount
        inc[to] = inc.get(to, 0) + amount
    return out, inc


@pytest.mark.parametrize("expenses, canon", [(V23, CANON), (V24, CANON), (V61, list("ABCDE")), (V61, list("EDCBA"))],
                         ids=["v23", "v24", "v61", "v61-reversed-canonical"])
def test_vector_23_24_61_every_debtor_and_creditor_total_is_exact(expenses, canon):
    b = balances()
    nets = b.net_balances(expenses)[INR]
    out, inc = totals_per_user([tuple(t) for t in b.pairwise_edges(expenses, canonical=canon)[INR]])
    for u, n in nets.items():
        if n < 0:
            assert out.get(u, 0) == -n and inc.get(u, 0) == 0, f"debtor {u}"
        elif n > 0:
            assert inc.get(u, 0) == n and out.get(u, 0) == 0, f"creditor {u}"


def test_vector_61_pairwise_exact_creditor_totals_controlled_rounding():
    edges = balances().pairwise_edges(V61, canonical=list("ABCDE"))[INR]
    assert [tuple(t) for t in edges] == tr(("D", "C", 1), ("E", "A", 1), ("E", "B", 1))   # listed debtor, then creditor
    out, inc = totals_per_user([tuple(t) for t in edges])
    assert inc == {"A": 1, "B": 1, "C": 1} and out == {"D": 1, "E": 2}


def test_vector_61_other_canonical_order_changes_only_who_gets_which_unit():
    edges = balances().pairwise_edges(V61, canonical=list("EDCBA"))[INR]   # C and A swap priority
    out, inc = totals_per_user([tuple(t) for t in edges])
    assert inc == {"A": 1, "B": 1, "C": 1} and out == {"D": 1, "E": 2}
    assert [tuple(t) for t in edges] == tr(("E", "C", 1), ("E", "B", 1), ("D", "A", 1))
