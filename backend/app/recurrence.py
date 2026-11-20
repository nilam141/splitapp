"""Recurring expenses, pure part (business_rules 8 "Recurring expense when a member has left", vectors 36-38).
No database, no I/O, no floats. Dates are calendar dates (`datetime.date`); money is integer minor units.

Occurrence n of a rule is computed from the ANCHOR date, never from the previous occurrence, so a month-end clamp
does not drift: monthly from 01-31 is 01-31, 02-28, 03-31, 04-30 (vector 36); yearly from 2028-02-29 falls back to
02-28 in common years and returns to 02-29 in the next leap year (vector 37)."""
import calendar
from collections.abc import Hashable, Sequence
from datetime import date, timedelta
from functools import reduce
from math import gcd

from app.splits import MAX_SHARES, TOTAL_BP, SplitError, compute_split, split_weighted

INTERVALS = ("weekly", "fortnightly", "monthly", "yearly")
_MAX_CATCH_UP = 366  # most occurrences one run will create for one rule; the rest follow on the next run


def _add_months(anchor: date, months: int) -> date:
    index = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def occurrence(anchor: date, interval: str, n: int) -> date:
    """The n-th occurrence (n = 0 is the anchor itself)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if interval == "weekly":
        return anchor + timedelta(days=7 * n)
    if interval == "fortnightly":
        return anchor + timedelta(days=14 * n)
    if interval == "monthly":
        return _add_months(anchor, n)
    if interval == "yearly":
        return _add_months(anchor, 12 * n)
    raise ValueError(f"unknown interval {interval!r}")


def next_after(anchor: date, interval: str, after: date) -> date:
    """The first occurrence strictly after `after` (and after the anchor)."""
    n = 1
    if after > anchor:  # jump close to the answer, then walk the last steps
        days = (after - anchor).days
        n = max(1, {"weekly": days // 7, "fortnightly": days // 14, "monthly": days // 31,
                    "yearly": days // 366}[interval])
    while occurrence(anchor, interval, n) <= after:
        n += 1
    while n > 1 and occurrence(anchor, interval, n - 1) > after:
        n -= 1
    return occurrence(anchor, interval, n)


def due_dates(anchor: date, interval: str, next_date: date, today: date, limit: int = _MAX_CATCH_UP) -> list[date]:
    """Every occurrence from `next_date` (a date on the rule's grid) up to and including `today`, oldest first.
    Used for catch-up after an outage: nothing is skipped, and nothing before `next_date` is repeated."""
    out: list[date] = []
    d = next_date
    while d <= today and len(out) < limit:
        out.append(d)
        d = next_after(anchor, interval, d)
    return out


# ---------- member left: rebuild the split over the people who remain ----------
Entry = tuple[Hashable, int | None]


def rebase_split(split_type: str, total: int, entries: Sequence[tuple[Hashable, int | None, int]],
                 remaining: set[Hashable]) -> tuple[str, list[Entry]]:
    """Drop the people who left from a stored split and return `(split_type, entries)` that `compute_split` accepts.

    `entries` are the stored rows `(user, input_value, owed_amount_minor)` in canonical order. The result keeps the
    order and has only users in `remaining`. Rules (business_rules 8, OQ-16):
    - equal: the same type over the remaining people;
    - percent: remaining weights re-normalised to 10000 bp (largest remainder), still percent (50/30/20 minus the 20
      gives 6250/3750, so 62.5% / 37.5%);
    - shares: the remaining share counts as they are (shares are weights already);
    - exact: becomes shares, using the old owed amounts as weights (scaled down into 0..999 only when needed);
    - adjustment: the remaining adjustments; if they now exceed the total, falls back to equal.
    Any case that cannot be expressed (all weights zero) falls back to equal. Raises ValueError if nobody remains."""
    kept = [(u, v, owed) for u, v, owed in entries if u in remaining]
    if not kept:
        raise ValueError("no participant remains")
    equal: list[Entry] = [(u, None) for u, _, _ in kept]
    if len(kept) == len(entries) or split_type == "equal":
        if split_type == "equal":
            return "equal", equal
        return split_type, [(u, v) for u, v, _ in kept]  # nobody left: unchanged
    if split_type == "shares":
        shares = [(u, v or 0) for u, v, _ in kept]
        return ("shares", shares) if sum(v for _, v in shares) >= 1 else ("equal", equal)
    if split_type == "percent":
        weights = [(u, v or 0) for u, v, _ in kept]
        if sum(w for _, w in weights) < 1:
            return "equal", equal
        bp = split_weighted(TOTAL_BP, weights)
        return "percent", [(u, bp[u]) for u, _ in weights]
    if split_type == "exact":
        weights = [(u, owed) for u, _, owed in kept]
        top = max(w for _, w in weights)
        if top < 1:
            return "equal", equal
        g = reduce(gcd, (w for _, w in weights))  # 6000:3000 -> 2:1 keeps the ratio exact
        weights = [(u, w // g) for u, w in weights]
        top //= g
        if top > MAX_SHARES:  # scale into 0..999; a person who owed something keeps at least 1 share
            weights = [(u, 0 if w == 0 else max(1, w * MAX_SHARES // top)) for u, w in weights]
        return "shares", weights
    if split_type == "adjustment":
        adjustments = [(u, v or 0) for u, v, _ in kept]
        if sum(a for _, a in adjustments) > total:
            return "equal", equal
        return "adjustment", adjustments
    raise ValueError(f"cannot rebase split type {split_type!r}")


def rebase_payers(total: int, payers: Sequence[tuple[Hashable, int]], remaining: set[Hashable]
                  ) -> list[tuple[Hashable, int]] | None:
    """Payers who left are dropped and the remaining paid amounts are scaled (largest remainder) to the total.
    Returns None when no payer remains (the caller deactivates the rule)."""
    kept = [(u, p) for u, p in payers if u in remaining]
    if not kept:
        return None
    if len(kept) == len(payers):
        return list(payers)
    scaled = split_weighted(total, kept)
    return [(u, scaled[u]) for u, _ in kept if scaled[u] > 0]


def occurrence_amounts(split_type: str, total: int, entries: Sequence[tuple[Hashable, int | None, int]],
                       remaining: set[Hashable]) -> tuple[str, list[Entry], dict[Hashable, int]]:
    """`rebase_split` plus the owed amounts of the new occurrence (vector 38: Rent 3,000,000 equal A, B, C with B
    gone gives A 1,500,000 and C 1,500,000). May raise ValueError (nobody left) or SplitError."""
    new_type, new_entries = rebase_split(split_type, total, entries, remaining)
    return new_type, new_entries, compute_split(new_type, total, new_entries)


__all__ = ["INTERVALS", "SplitError", "due_dates", "next_after", "occurrence", "occurrence_amounts", "rebase_payers",
           "rebase_split"]
