"""Backend-owned tests for app/splits.py: the branches the vector tables do not reach (S3-B-1, 100% branch coverage).

Run `coverage run --branch --include=app/splits.py -m pytest tests/rules tests/test_splits_engine.py` to check it.
"""
import pytest

from app import splits as s


def code(fn, *args):
    with pytest.raises(s.SplitError) as ei:
        fn(*args)
    return ei.value


def test_split_error_carries_code_and_details():
    err = s.SplitError("X", {"a": 1})
    assert (err.code, err.details, str(err)) == ("X", {"a": 1}, "X")
    assert s.SplitError("Y").details is None


def test_validate_total_bounds():
    for ok in (1, s.MAX_TOTAL):
        s.validate_total(ok)
    for bad in (0, -5, s.MAX_TOTAL + 1):
        assert code(s.validate_total, bad).code == "AMOUNT_OUT_OF_RANGE"


def test_validate_payers_non_positive_amount_is_validation_error():
    err = code(s.validate_payers, 100, [("A", 0), ("B", 100)])
    assert err.code == "VALIDATION_ERROR" and err.details["fields"][0]["field"] == "payers"


def test_validate_payers_ok_and_empty_list_is_a_mismatch():
    s.validate_payers(100, [("A", 60), ("B", 40)])
    err = code(s.validate_payers, 100, [])
    assert err.code == "PAYER_SUM_MISMATCH" and err.details == {"expected": 100, "actual": 0, "difference": -100}


def test_net_amounts_merges_users_present_in_both():
    assert s.net_amounts([("A", 100)], {"A": 40, "B": 60}) == {"A": 60, "B": -60}


def test_out_of_range_inputs_are_validation_errors():
    for fn, entries in ((s.split_exact, [("A", -1), ("B", 101)]), (s.split_percent, [("A", 10001), ("B", -1)]),
                        (s.split_shares, [("A", 1000)]), (s.split_adjustment, [("A", -5)])):
        err = code(fn, 100, entries)
        assert err.code == "VALIDATION_ERROR" and err.details["fields"][0]["field"] == "split.entries"


def test_every_typed_split_rejects_empty_and_duplicate_participants():
    for fn in (s.split_exact, s.split_percent, s.split_shares, s.split_adjustment):
        assert code(fn, 100, []).code == "SPLIT_NO_PARTICIPANTS"
        assert code(fn, 100, [("A", 1), ("A", 1)]).code == "DUPLICATE_PARTICIPANT"


def test_compute_split_dispatches_every_type():
    ids = ["A", "B", "C"]
    assert s.compute_split("equal", 100, [(u, 999) for u in ids]) == {"A": 34, "B": 33, "C": 33}
    assert s.compute_split("exact", 100, [("A", 100), ("B", None)]) == {"A": 100, "B": 0}
    assert s.compute_split("percent", 100, [("A", 2500), ("B", 7500)]) == {"A": 25, "B": 75}
    assert s.compute_split("shares", 100, [("A", 1), ("B", 3)]) == {"A": 25, "B": 75}
    assert s.compute_split("adjustment", 100, [("A", 10), ("B", None)]) == {"A": 55, "B": 45}


def test_compute_split_unknown_type():
    err = code(s.compute_split, "itemized", 100, [("A", 1)])
    assert err.code == "VALIDATION_ERROR" and err.details["fields"][0]["field"] == "split.type"


def test_results_are_plain_ints_even_at_the_maximum():
    out = s.split_percent(s.MAX_TOTAL, [("A", 3333), ("B", 3333), ("C", 3334)])
    assert sum(out.values()) == s.MAX_TOTAL and all(type(v) is int for v in out.values())
