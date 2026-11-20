"""Split engine and amount validation (business_rules 1-3). Pure functions: no database, no I/O, no floats.

All amounts are integer minor units. Participants are passed in canonical order (business_rules 1) and every
result is a dict in that same order, so a caller that stores `sort_index` from the input order reproduces it.
Ids are opaque hashable values (the service passes UUIDs; the tests pass strings).
"""
from collections.abc import Hashable, Sequence
from typing import Any

MAX_TOTAL = 9_999_999_999
MAX_SHARES = 999
TOTAL_BP = 10_000

Entry = tuple[Hashable, int]


class SplitError(Exception):
    """A rule violation. `code` is an openapi `Error.code`; `details` is the exact `Error.details` object (or None)."""

    def __init__(self, code: str, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details


def _invalid(field: str, message: str) -> SplitError:
    return SplitError("VALIDATION_ERROR", {"fields": [{"field": field, "message": message}]})


# ---------- validation ----------
def validate_total(total: int) -> None:
    """1 <= T <= 9,999,999,999, otherwise AMOUNT_OUT_OF_RANGE (business_rules 1, 2; vector 34)."""
    if not 1 <= total <= MAX_TOTAL:
        raise SplitError("AMOUNT_OUT_OF_RANGE")


def validate_payers(total: int, payers: Sequence[Entry]) -> None:
    """Payers are unique and each paid > 0; their sum must equal the total (business_rules 3)."""
    seen: set[Hashable] = set()
    for user, paid in payers:
        if user in seen:
            raise SplitError("DUPLICATE_PAYER")
        seen.add(user)
        if paid < 1:
            raise _invalid("payers", "paid_amount_minor must be at least 1")
    actual = sum(paid for _, paid in payers)
    if actual != total:
        raise SplitError("PAYER_SUM_MISMATCH", {"expected": total, "actual": actual, "difference": actual - total})


def net_amounts(payers: Sequence[Entry], owed: dict[Hashable, int]) -> dict[Hashable, int]:
    """net = paid - owed for every user that appears in either input (zeros kept)."""
    net: dict[Hashable, int] = {}
    for user, paid in payers:
        net[user] = net.get(user, 0) + paid
    for user, amount in owed.items():
        net[user] = net.get(user, 0) - amount
    return net


def _check_participants(ids: Sequence[Hashable]) -> None:
    if not ids:
        raise SplitError("SPLIT_NO_PARTICIPANTS")
    if len(set(ids)) != len(ids):
        raise SplitError("DUPLICATE_PARTICIPANT")


def _check_entries(entries: Sequence[Entry], field: str, upper: int | None = None) -> None:
    _check_participants([user for user, _ in entries])
    for _, value in entries:
        if value < 0 or (upper is not None and value > upper):
            raise _invalid(field, "value out of range")


# ---------- the five split types ----------
def split_equal(total: int, participants: Sequence[Hashable]) -> dict[Hashable, int]:
    """base = T div n; the first T mod n participants in canonical order get one extra unit."""
    _check_participants(participants)
    base, extra = divmod(total, len(participants))
    return {user: base + (1 if i < extra else 0) for i, user in enumerate(participants)}


def split_exact(total: int, entries: Sequence[Entry]) -> dict[Hashable, int]:
    """Entries are the owed amounts; they must add up to the total."""
    _check_entries(entries, "split.entries")
    actual = sum(value for _, value in entries)
    if actual != total:
        raise SplitError("SPLIT_SUM_MISMATCH", {"expected": total, "actual": actual, "difference": actual - total})
    return {user: value for user, value in entries}


def _split_weighted(total: int, weights: Sequence[Entry]) -> dict[Hashable, int]:
    """Largest remainder (Hamilton): floors first, then one unit each to the largest fractional parts, ties by
    canonical order. The weight sum must be positive."""
    weight_sum = sum(w for _, w in weights)
    owed: dict[Hashable, int] = {}
    fractions: list[tuple[int, int, Hashable]] = []
    for i, (user, w) in enumerate(weights):
        whole, frac = divmod(total * w, weight_sum)
        owed[user] = whole
        fractions.append((frac, i, user))
    leftover = total - sum(owed.values())
    for _, _, user in sorted(fractions, key=lambda f: (-f[0], f[1]))[:leftover]:
        owed[user] += 1
    return owed


def split_percent(total: int, entries: Sequence[Entry]) -> dict[Hashable, int]:
    """Entries are basis points (3333 = 33.33%); they must add up to 10000."""
    _check_entries(entries, "split.entries", TOTAL_BP)
    difference = sum(bp for _, bp in entries) - TOTAL_BP
    if difference != 0:
        raise SplitError("SPLIT_PERCENT_MISMATCH", {"difference_bp": difference})
    return _split_weighted(total, entries)


def split_shares(total: int, entries: Sequence[Entry]) -> dict[Hashable, int]:
    """Entries are integer share counts 0..999; at least one share overall. A zero-share participant owes 0."""
    _check_entries(entries, "split.entries", MAX_SHARES)
    if sum(s for _, s in entries) < 1:
        raise SplitError("SPLIT_NO_SHARES")
    return _split_weighted(total, entries)


def split_adjustment(total: int, entries: Sequence[Entry]) -> dict[Hashable, int]:
    """Entries are extra amounts a person owes; the rest (T - sum) is split equally over everyone."""
    _check_entries(entries, "split.entries")
    adjusted = sum(a for _, a in entries)
    if adjusted > total:
        raise SplitError("SPLIT_ADJUSTMENT_EXCEEDS_TOTAL",
                         {"expected": total, "actual": adjusted, "difference": adjusted - total})
    equal = split_equal(total - adjusted, [user for user, _ in entries])
    return {user: a + equal[user] for user, a in entries}


def compute_split(split_type: str, total: int, entries: Sequence[tuple[Hashable, int | None]]) -> dict[Hashable, int]:
    """Dispatch on the split type. `entries` are (user, value) in canonical order; equal ignores the value."""
    if split_type == "equal":
        return split_equal(total, [user for user, _ in entries])
    fn = {"exact": split_exact, "percent": split_percent, "shares": split_shares,
          "adjustment": split_adjustment}.get(split_type)
    if fn is None:
        raise _invalid("split.type", "unknown split type")
    return fn(total, [(user, 0 if value is None else value) for user, value in entries])
