"""Group timeline (S3-B-6): a read-time merge of the group's dated items, newest first.

Every source returns its own next `limit` items strictly after the cursor key, already ordered by
(date desc, created_at desc, id desc); the merge sorts the union on the same key and cuts at `limit`. Until S5-B-4 the
only source is expenses. The settlement source joins SOURCES then, with `settled_on` as its date; nothing else changes,
and the paging stays a keyset over (date, created_at, id), so inserts and deletes between pages never duplicate or
skip an item that existed at both times."""
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services_expenses as svc
from app.models import Expense, User
from app.pagination import Key, decode, encode
from app.schemas_expenses import TimelineExpense, TimelinePage
from app.services_groups import _load_for_member

Item = tuple[Key, TimelineExpense]  # S5-B-4 widens the value to a union with TimelineSettlement
Source = Callable[[Session, User, uuid.UUID, bool, Key | None, int], list[Item]]


def _expense_source(db: Session, me: User, group_id: uuid.UUID, include_deleted: bool, after: Key | None,
                    limit: int) -> list[Item]:
    base = select(Expense).where(Expense.group_id == group_id)
    if not include_deleted:
        base = base.where(Expense.deleted_at.is_(None))
    rows = svc.expense_rows(db, base, after, limit)
    return [(svc.expense_key(e), TimelineExpense(date=e.expense_date, expense=out))
            for e, out in zip(rows, svc._outs(db, rows, me.id))]


SOURCES: list[Source] = [_expense_source]


def list_timeline(db: Session, me: User, group_id: uuid.UUID, limit: int, cursor: str | None,
                  include_deleted: bool) -> TimelinePage:
    _load_for_member(db, me, group_id)  # 404 unknown group, 403 not a current member
    after = decode(cursor, dated=True) if cursor else None
    merged: list[Item] = []
    for source in SOURCES:
        merged.extend(source(db, me, group_id, include_deleted, after, limit + 1))
    merged.sort(key=lambda item: (item[0].day, item[0].created_at, str(item[0].id)), reverse=True)
    more = len(merged) > limit
    page = merged[:limit]
    return TimelinePage(items=[item for _, item in page], next_cursor=encode(page[-1][0]) if more else None)
