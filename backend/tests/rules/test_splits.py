"""S3-Q-1: split engine and amount validation, one parametrised row per business_rules vector.

Vectors 1-18, 13b and 34 live in vectors.json (shared with mobile S3-M-2). All amounts are integer minor units.
Participants are listed in canonical order; the engine receives them in that order and must keep it.
"""
import json
from pathlib import Path

import pytest

from tests.rules.engine import engine

VECTORS = json.loads((Path(__file__).parent / "vectors.json").read_text())["vectors"]
IDS = [f"v{v['id']}" for v in VECTORS]
EXPECTED_IDS = [str(i) for i in range(1, 19)] + ["13b", "34a", "34b", "34c"]


def test_vector_table_is_complete():
    """Guards the table itself: every vector 1-18, 13b and 34 (three rows) is present exactly once."""
    assert sorted(v["id"] for v in VECTORS) == sorted(EXPECTED_IDS)


def run_split(eng, v):
    t, entries = v["total"], v["entries"]
    kind = v["split_type"]
    if kind == "equal":
        return eng.split_equal(t, [u for u, _ in entries])
    fn = {"exact": eng.split_exact, "percent": eng.split_percent, "shares": eng.split_shares,
          "adjustment": eng.split_adjustment}[kind]
    return fn(t, [(u, val) for u, val in entries])


def expect_error(eng, expected, fn):
    with pytest.raises(eng.SplitError) as ei:
        fn()
    assert ei.value.code == expected["code"]
    if "details" in expected:
        assert ei.value.details == expected["details"]  # exact keys and values, nothing extra


@pytest.mark.parametrize("v", [v for v in VECTORS if v["kind"] == "split"],
                         ids=[f"v{v['id']}" for v in VECTORS if v["kind"] == "split"])
def test_split_vectors(v):
    eng = engine()
    exp = v["expected"]
    if "error" in exp:
        expect_error(eng, exp["error"], lambda: run_split(eng, v))
        return
    result = run_split(eng, v)
    assert list(result.items()) == [tuple(p) for p in exp["owed"]]  # exact numbers, canonical order
    assert sum(result.values()) == v["total"]
    assert all(type(x) is int for x in result.values())


@pytest.mark.parametrize("v", [v for v in VECTORS if v["kind"] == "expense"],
                         ids=[f"v{v['id']}" for v in VECTORS if v["kind"] == "expense"])
def test_payer_vectors(v):
    """Vectors 5, 17, 18: payers validated against the total, then net = paid - owed per user."""
    eng = engine()
    payers = [tuple(p) for p in v["payers"]]
    exp = v["expected"]
    if "error" in exp:
        expect_error(eng, exp["error"], lambda: eng.validate_payers(v["total"], payers))
        return
    eng.validate_payers(v["total"], payers)
    owed = run_split(eng, v)
    assert list(owed.items()) == [tuple(p) for p in exp["owed"]]
    assert eng.net_amounts(payers, owed) == exp["nets"]


@pytest.mark.parametrize("v", [v for v in VECTORS if v["kind"] == "bounds"],
                         ids=[f"v{v['id']}" for v in VECTORS if v["kind"] == "bounds"])
def test_amount_bounds(v):
    eng = engine()
    exp = v["expected"]
    if "error" in exp:
        expect_error(eng, exp["error"], lambda: eng.validate_total(v["total"]))
    else:
        eng.validate_total(v["total"])  # must not raise
        assert sum(eng.split_equal(v["total"], ["A", "B", "C"]).values()) == v["total"]  # max T splits exactly


# ---- documented rules that have no numbered vector (codes only; the docs give no `details` for them) -----------------

def test_equal_needs_a_participant():
    eng = engine()
    expect_error(eng, {"code": "SPLIT_NO_PARTICIPANTS"}, lambda: eng.split_equal(100, []))


def test_shares_need_at_least_one_share():
    eng = engine()
    expect_error(eng, {"code": "SPLIT_NO_SHARES"}, lambda: eng.split_shares(100, [("A", 0), ("B", 0)]))


def test_zero_shares_participant_owes_zero_but_stays_in_the_result():
    eng = engine()
    assert list(eng.split_shares(100, [("A", 0), ("B", 3)]).items()) == [("A", 0), ("B", 100)]


def test_duplicate_payer():
    eng = engine()
    expect_error(eng, {"code": "DUPLICATE_PAYER"}, lambda: eng.validate_payers(100, [("A", 50), ("A", 50)]))


def test_duplicate_participant():
    eng = engine()
    expect_error(eng, {"code": "DUPLICATE_PARTICIPANT"}, lambda: eng.split_equal(100, ["A", "A"]))
    expect_error(eng, {"code": "DUPLICATE_PARTICIPANT"}, lambda: eng.split_exact(100, [("A", 50), ("A", 50)]))


def test_exact_split_over_reports_positive_difference():
    eng = engine()
    expect_error(eng, {"code": "SPLIT_SUM_MISMATCH", "details": {"expected": 100, "actual": 130, "difference": 30}},
                 lambda: eng.split_exact(100, [("A", 100), ("B", 30)]))


def test_percent_over_reports_positive_difference_bp():
    eng = engine()
    expect_error(eng, {"code": "SPLIT_PERCENT_MISMATCH", "details": {"difference_bp": 100}},
                 lambda: eng.split_percent(1000, [("A", 5000), ("B", 5100)]))


def test_percent_tie_goes_to_canonical_order():
    """Equal fractional parts: the earlier participant in canonical order gets the leftover unit (business_rules 2.3)."""
    eng = engine()
    # T=1 over 5000/5000 bp: both fractions are 0.5, one leftover unit -> first participant.
    assert list(eng.split_percent(1, [("A", 5000), ("B", 5000)]).items()) == [("A", 1), ("B", 0)]
    assert list(eng.split_percent(1, [("B", 5000), ("A", 5000)]).items()) == [("B", 1), ("A", 0)]


def test_adjustment_all_of_total_leaves_nothing_to_split():
    eng = engine()
    assert list(eng.split_adjustment(100, [("A", 60), ("B", 40), ("C", 0)]).items()) == [("A", 60), ("B", 40), ("C", 0)]


def test_net_amounts_payer_outside_split_has_no_owed():
    eng = engine()
    assert eng.net_amounts([("A", 100)], {"B": 50, "C": 50}) == {"A": 100, "B": -50, "C": -50}
