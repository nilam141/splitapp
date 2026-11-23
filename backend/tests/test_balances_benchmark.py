"""S4-B-2: p95 of GET /groups/{id}/balances with 5,000 live expenses stays under 200 ms (data_model "Derived data").
Rows are bulk-inserted (the HTTP path is covered elsewhere). Timed with pytest-benchmark. The threshold is enforced on
PostgreSQL (TEST_DATABASE_URL); on in-memory SQLite the same measurement runs and is reported but only a generous
bound (2 s) is asserted, because the 200 ms target is about the production engine."""
import gc
import math
import statistics
import uuid
from datetime import date

from sqlalchemy import insert

from app.models import Expense, ExpensePayer, ExpenseSplit
from tests.conftest import PG_URL
from tests.expense_helpers import h, make_group, uid, user

N_EXPENSES = 5000
ROUNDS = 120


def _seed(db_session, gid, member_ids, creator):
    expenses, payers, splits = [], [], []
    for i in range(N_EXPENSES):
        eid = uuid.uuid4()
        total = 1000 + (i % 97) * 7
        payer = member_ids[i % len(member_ids)]
        expenses.append(dict(id=eid, group_id=uuid.UUID(gid), description=f"E{i}", total_amount_minor=total,
                             currency="INR" if i % 5 else "USD", category_id=1, expense_date=date(2026, 11, 5),
                             split_type="equal", created_by=creator, version=1))
        payers.append(dict(expense_id=eid, user_id=payer, paid_amount_minor=total))
        base, extra = divmod(total, len(member_ids))
        for k, m in enumerate(member_ids):
            splits.append(dict(expense_id=eid, user_id=m, owed_amount_minor=base + (1 if k < extra else 0),
                               sort_index=k))
    db_session.execute(insert(Expense), expenses)
    db_session.execute(insert(ExpensePayer), payers)
    db_session.execute(insert(ExpenseSplit), splits)
    db_session.commit()


def test_group_balances_p95_under_200ms_with_5000_expenses(client, db_session, benchmark):
    people = [user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev", "Isha")]
    gid = make_group(client, people[0], people[1:])
    ids = [uuid.UUID(uid(p)) for p in people]
    _seed(db_session, gid, ids, ids[0])
    headers = h(people[0])

    def call():
        r = client.get(f"/groups/{gid}/balances", headers=headers)
        assert r.status_code == 200
        return r

    # Robust measurement: warm-up (caches, plan cache), then 120 timed rounds so p95 is a real percentile (the 6th
    # slowest, not the 2nd of 40), with the garbage collector paused during timing.
    for _ in range(10):
        call()
    gc.collect()
    gc.disable()
    try:
        r = benchmark.pedantic(call, rounds=ROUNDS, iterations=1, warmup_rounds=0)
    finally:
        gc.enable()
    body = r.json()
    for cur in ("INR", "USD"):  # nets of every currency add up to zero
        assert sum(b["amount_minor"] for m in body["members"] for b in m["balances"] if b["currency"] == cur) == 0
    data = sorted(benchmark.stats.stats.data)
    p95 = data[math.ceil(len(data) * 0.95) - 1]  # nearest-rank 95th percentile
    print(f"\nGET /groups/{{id}}/balances, {N_EXPENSES} expenses, {len(data)} rounds: "
          f"median {statistics.median(data) * 1000:.1f} ms, p95 {p95 * 1000:.1f} ms, max {data[-1] * 1000:.1f} ms")
    assert p95 < (0.2 if PG_URL else 2.0), p95
