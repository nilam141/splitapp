"""S6-Q-1 / S6-B-1 / S6-B-2: the pure recurrence module (no database). Vectors 36, 37, 38 from business_rules.md."""
from datetime import date, timedelta

import pytest

from app import recurrence as rc


def seq(anchor, interval, n):
    return [rc.occurrence(anchor, interval, i) for i in range(n)]


def test_vector_36_monthly_month_end_clamp():
    assert seq(date(2026, 1, 31), "monthly", 4) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_vector_37_yearly_leap_day():
    assert seq(date(2028, 2, 29), "yearly", 5) == [
        date(2028, 2, 29), date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29)]


def test_fortnightly_from_2026_01_01():
    assert seq(date(2026, 1, 1), "fortnightly", 3) == [date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)]


def test_weekly_and_month_rollover_across_years():
    assert seq(date(2026, 12, 28), "weekly", 3) == [date(2026, 12, 28), date(2027, 1, 4), date(2027, 1, 11)]
    assert rc.occurrence(date(2026, 11, 30), "monthly", 3) == date(2027, 2, 28)
    assert rc.occurrence(date(2026, 1, 31), "monthly", 13) == date(2027, 2, 28)


def test_the_clamp_does_not_drift_it_is_computed_from_the_anchor():
    # Feb 28 -> Mar 31 (not Mar 28): occurrence n is derived from the anchor, never from the previous date
    assert rc.next_after(date(2026, 1, 31), "monthly", date(2026, 2, 28)) == date(2026, 3, 31)


def test_next_after_is_strictly_after_and_on_the_grid():
    anchor = date(2026, 1, 31)
    assert rc.next_after(anchor, "monthly", anchor) == date(2026, 2, 28)
    assert rc.next_after(anchor, "monthly", date(2026, 2, 27)) == date(2026, 2, 28)
    assert rc.next_after(anchor, "monthly", date(2026, 2, 28)) == date(2026, 3, 31)
    assert rc.next_after(anchor, "monthly", date(2020, 1, 1)) == date(2026, 2, 28)  # before the anchor: first after it
    for interval in rc.INTERVALS:
        for start in (date(2024, 2, 29), date(2026, 1, 31), date(2026, 3, 1)):
            grid = seq(start, interval, 40)
            for i in range(len(grid) - 1):
                for probe in (grid[i], grid[i] + timedelta(days=1)):
                    if probe < grid[i + 1]:
                        assert rc.next_after(start, interval, probe) == grid[i + 1], (interval, start, probe)


def test_catch_up_after_a_three_day_outage_loses_nothing_and_repeats_nothing():
    # daily-ish check: weekly from Mon 2026-01-05; the job did not run on 01-12, 01-13, 01-14
    anchor = date(2026, 1, 5)
    assert rc.due_dates(anchor, "weekly", date(2026, 1, 12), date(2026, 1, 14)) == [date(2026, 1, 12)]
    # fortnightly, next due 01-15, job back on 01-31: both missed dates, in order
    assert rc.due_dates(date(2026, 1, 1), "fortnightly", date(2026, 1, 15), date(2026, 1, 31)) == [
        date(2026, 1, 15), date(2026, 1, 29)]
    # nothing due yet
    assert rc.due_dates(date(2026, 1, 1), "fortnightly", date(2026, 1, 15), date(2026, 1, 14)) == []


def test_catch_up_is_capped_per_run():
    out = rc.due_dates(date(2020, 1, 1), "weekly", date(2020, 1, 8), date(2030, 1, 1), limit=10)
    assert len(out) == 10 and out[0] == date(2020, 1, 8)


# ---------- vector 38: a member left ----------
A, B, C = "A", "B", "C"


def rows3(split_type, values, owed):
    return [(u, v, o) for u, v, o in zip((A, B, C), values, owed)]


def test_vector_38_equal_rent_after_b_left():
    t, entries, owed = rc.occurrence_amounts("equal", 3_000_000, rows3("equal", (None,) * 3, (1_000_000,) * 3), {A, C})
    assert t == "equal" and owed == {A: 1_500_000, C: 1_500_000}


def test_equal_remainder_goes_to_the_first_in_canonical_order():
    _, _, owed = rc.occurrence_amounts("equal", 100, rows3("equal", (None,) * 3, (34, 33, 33)), {A, C})
    assert owed == {A: 50, C: 50}
    _, _, owed = rc.occurrence_amounts("equal", 101, rows3("equal", (None,) * 3, (34, 34, 33)), {A, C})
    assert owed == {A: 51, C: 50}


def test_percent_renormalises_50_30_20_to_62_5_and_37_5():
    t, entries, owed = rc.occurrence_amounts("percent", 100_000, rows3("percent", (5000, 3000, 2000), (50_000, 30_000, 20_000)), {A, B})
    assert t == "percent" and entries == [(A, 6250), (B, 3750)]
    assert owed == {A: 62_500, B: 37_500}


def test_percent_renormalisation_always_sums_to_10000():
    _, entries, owed = rc.occurrence_amounts("percent", 999, rows3("percent", (3334, 3333, 3333), (0, 0, 0)), {A, C})
    assert sum(v for _, v in entries) == 10_000 and sum(owed.values()) == 999


def test_shares_keep_their_weights():
    t, entries, owed = rc.occurrence_amounts("shares", 90_000, rows3("shares", (2, 1, 3), (0, 0, 0)), {A, C})
    assert t == "shares" and entries == [(A, 2), (C, 3)] and owed == {A: 36_000, C: 54_000}


def test_exact_becomes_shares_weighted_by_the_old_amounts():
    t, entries, owed = rc.occurrence_amounts("exact", 10_000, rows3("exact", (6000, 3000, 1000), (6000, 3000, 1000)), {A, B})
    assert t == "shares" and sum(owed.values()) == 10_000
    assert owed == {A: 6667, B: 3333}  # 6000:3000 of 10000 -> largest remainder
    assert all(0 <= v <= 999 for _, v in entries)  # shares stay inside the 0..999 contract range


def test_exact_with_a_large_weight_is_scaled_into_the_share_range():
    _, entries, owed = rc.occurrence_amounts("exact", 9_000_000_000, rows3("exact", (6_000_000_000, 2_000_000_000, 1_000_000_000), (6_000_000_000, 2_000_000_000, 1_000_000_000)), {A, C})
    assert max(v for _, v in entries) <= 999 and sum(owed.values()) == 9_000_000_000


def test_adjustment_keeps_remaining_adjustments_or_falls_back_to_equal():
    t, entries, owed = rc.occurrence_amounts("adjustment", 1000, rows3("adjustment", (100, 200, 300), (0, 0, 0)), {A, C})
    assert t == "adjustment" and entries == [(A, 100), (C, 300)] and owed == {A: 100 + 300, C: 300 + 300}
    t, entries, owed = rc.occurrence_amounts("adjustment", 1000, rows3("adjustment", (100, 200, 900), (0, 0, 0)), {A, C})
    assert t == "adjustment" and owed == {A: 100, C: 900}  # 100 + 900 = 1000 uses the whole total: still valid


def test_adjustment_over_total_falls_back_to_equal():
    t, _, owed = rc.occurrence_amounts("adjustment", 1000, rows3("adjustment", (600, 100, 600), (0, 0, 0)), {A, C})
    assert t == "equal" and owed == {A: 500, C: 500}


def test_nobody_left_raises():
    with pytest.raises(ValueError):
        rc.rebase_split("equal", 100, rows3("equal", (None,) * 3, (34, 33, 33)), set())


def test_nothing_changes_when_nobody_left():
    t, entries, owed = rc.occurrence_amounts("percent", 100, rows3("percent", (5000, 3000, 2000), (50, 30, 20)), {A, B, C})
    assert t == "percent" and owed == {A: 50, B: 30, C: 20}


def test_payers_rebase():
    assert rc.rebase_payers(3000, [(A, 3000)], {A, C}) == [(A, 3000)]
    assert rc.rebase_payers(3000, [(A, 1000), (B, 2000)], {A, C}) == [(A, 3000)]
    assert rc.rebase_payers(3000, [(A, 1000), (B, 1000), (C, 1000)], {A, C}) == [(A, 1500), (C, 1500)]
    assert rc.rebase_payers(3000, [(B, 3000)], {A, C}) is None
