"""S3-Q-2: property tests for business_rules vector 39 (hypothesis, 10,000 examples per split type).

For T in [1, 9,999,999,999] and 1-50 participants, for every split type: sum(owed) == T, every owed >= 0, and the same
input gives the same output. Extra invariants that follow directly from the rules (equal: spread <= 1; weighted:
each share within 1 unit of its exact quota; result keys keep canonical order).
"""
from hypothesis import HealthCheck, given, settings, strategies as st

from tests.rules.engine import engine

MAX_T = 9_999_999_999
EXAMPLES = 10_000
CFG = settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck), database=None)

totals = st.integers(min_value=1, max_value=MAX_T)
counts = st.integers(min_value=1, max_value=50)


def ids(n):
    return [f"u{i:02d}" for i in range(n)]


@st.composite
def partition(draw, total, parts):
    """`parts` non-negative integers summing to `total`."""
    cuts = sorted(draw(st.lists(st.integers(0, total), min_size=parts - 1, max_size=parts - 1)))
    edges = [0] + cuts + [total]
    return [edges[i + 1] - edges[i] for i in range(parts)]


def check_common(eng_fn, total, args):
    out = eng_fn(total, args)
    assert sum(out.values()) == total
    assert all(type(x) is int and x >= 0 for x in out.values())
    assert eng_fn(total, args) == out  # deterministic
    return out


@CFG
@given(total=totals, n=counts)
def test_equal_sums_and_spread(total, n):
    eng = engine()
    users = ids(n)
    out = check_common(eng.split_equal, total, users)
    assert list(out) == users
    assert max(out.values()) - min(out.values()) <= 1
    assert list(out.values()) == sorted(out.values(), reverse=True)  # leftover units go to the earliest participants


@CFG
@given(data=st.data(), total=totals, n=counts)
def test_exact_sums(data, total, n):
    eng = engine()
    amounts = data.draw(partition(total, n))
    entries = list(zip(ids(n), amounts))
    out = check_common(eng.split_exact, total, entries)
    assert list(out.items()) == entries  # inputs are already integers: returned unchanged


@CFG
@given(data=st.data(), total=totals, n=counts)
def test_percent_sums_and_quota(data, total, n):
    eng = engine()
    bps = data.draw(partition(10000, n))
    entries = list(zip(ids(n), bps))
    out = check_common(eng.split_percent, total, entries)
    assert list(out) == ids(n)
    for (u, bp), owed in zip(entries, out.values()):  # largest remainder: within 1 unit of the exact quota
        assert abs(owed * 10000 - total * bp) < 10000


@CFG
@given(data=st.data(), total=totals, n=counts)
def test_shares_sums_and_quota(data, total, n):
    eng = engine()
    shares = data.draw(st.lists(st.integers(0, 999), min_size=n, max_size=n).filter(lambda s: sum(s) >= 1))
    entries = list(zip(ids(n), shares))
    out = check_common(eng.split_shares, total, entries)
    W = sum(shares)
    for (u, w), owed in zip(entries, out.values()):
        assert abs(owed * W - total * w) < W
        if w == 0:
            assert owed == 0


@CFG
@given(data=st.data(), total=totals, n=counts)
def test_adjustment_sums_and_floor(data, total, n):
    eng = engine()
    parts = data.draw(partition(total, n + 1))  # the last part is the "rest" to share equally
    adj = parts[:n]
    entries = list(zip(ids(n), adj))
    out = check_common(eng.split_adjustment, total, entries)
    assert all(owed >= a for (_, a), owed in zip(entries, out.values()))
    extra = [owed - a for (_, a), owed in zip(entries, out.values())]
    assert max(extra) - min(extra) <= 1
