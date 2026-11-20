"""Unit tests for the cursor codec and the timeline merge (S3-B-6 'built to take a second source')."""
import base64
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app import pagination, timeline
from app.errors import ApiError
from app.pagination import Key
from app.schemas_expenses import TimelineExpense
from tests.expense_helpers import create_group_expense, equal_body, make_group, user


def enc(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def test_cursor_round_trip_dated_and_undated():
    k = Key(date(2026, 11, 5), datetime(2026, 11, 5, 10, 0, 0, 123456, tzinfo=timezone.utc), uuid.uuid4())
    assert pagination.decode(pagination.encode(k), dated=True) == k
    u = Key(None, k.created_at, k.id)
    assert pagination.decode(pagination.encode(u), dated=False) == u
    naive = Key(k.day, datetime(2026, 11, 5, 10), k.id)  # SQLite rows are naive UTC
    assert pagination.decode(pagination.encode(naive), dated=True).created_at.hour == 10


def test_aware_normalises_to_utc():
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    assert pagination.aware(datetime(2026, 11, 5, 15, 30, tzinfo=ist)) == datetime(2026, 11, 5, 10, tzinfo=timezone.utc)
    assert pagination.aware(datetime(2026, 11, 5, 10)).tzinfo is timezone.utc


GOOD_ID = str(uuid.uuid4())


@pytest.mark.parametrize("raw", [
    "", "garbage", "!!!", "e30", "a" * 400, enc([]), enc({"a": 1, "b": 2, "c": 3}), enc("x"), enc([1, 2]),
    enc(["2026-11-05", "2026-11-05T10:00:00+00:00"]), enc([None, "2026-11-05T10:00:00+00:00", GOOD_ID]),  # no date
    enc(["2026-13-45", "2026-11-05T10:00:00+00:00", GOOD_ID]), enc(["2026-11-05", "nope", GOOD_ID]),
    enc(["2026-11-05", "2026-11-05T10:00:00", GOOD_ID]),  # naive timestamp
    enc(["2026-11-05", "2026-11-05T10:00:00+00:00", "not-a-uuid"]), enc(["2026-11-05", None, GOOD_ID]),
    base64.urlsafe_b64encode(b"\xff\xfe").decode(),
])
def test_malformed_cursors_are_rejected(raw):
    with pytest.raises(ApiError) as ei:
        pagination.decode(raw, dated=True)
    assert ei.value.status == 422 and ei.value.code == "VALIDATION_ERROR"
    assert ei.value.details["fields"][0]["field"] == "cursor"


def test_dated_cursor_is_not_valid_for_comments_and_vice_versa():
    k = Key(date(2026, 11, 5), datetime(2026, 11, 5, tzinfo=timezone.utc), uuid.uuid4())
    with pytest.raises(ApiError):
        pagination.decode(pagination.encode(k), dated=False)
    with pytest.raises(ApiError):
        pagination.decode(pagination.encode(Key(None, k.created_at, k.id)), dated=True)


def test_timeline_merges_a_second_source_in_one_keyset_order(client, db_session, monkeypatch):
    """A fake settlement-like source joins SOURCES; items interleave by (date, created_at, id) and page cleanly."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e1 = create_group_expense(client, a, gid, equal_body(a, [a, b], date="2026-11-05", description="E1"))
    e2 = create_group_expense(client, a, gid, equal_body(a, [a, b], date="2026-11-06", description="E2"))
    other = [(Key(date(2026, 11, 5), datetime(2099, 1, 1, tzinfo=timezone.utc), uuid.UUID(int=1)), "S1"),
             (Key(date(2026, 11, 4), datetime(2026, 11, 1, tzinfo=timezone.utc), uuid.UUID(int=2)), "S2")]

    def fake_source(db, me, group_id, include_deleted, after, limit):
        rows = [(k, v) for k, v in other if after is None or (k.day, k.created_at, str(k.id)) <
                (after.day, after.created_at, str(after.id))]
        return [(k, TimelineExpense.model_construct(kind="expense", date=k.day, expense=v)) for k, v in rows[:limit]]

    monkeypatch.setattr(timeline, "SOURCES", [*timeline.SOURCES, fake_source])
    from app.models import User
    db = db_session
    me = db.get(User, uuid.UUID(a["user"]["id"]))
    seen, cursor = [], None
    for _ in range(5):
        page = timeline.list_timeline(db, me, uuid.UUID(gid), 1, cursor, False)
        seen += [i.expense if isinstance(i.expense, str) else i.expense.description for i in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ["E2", "S1", "E1", "S2"]  # the vector 50 shape: settlement-like items interleave with expenses
    assert e1["id"] != e2["id"]
