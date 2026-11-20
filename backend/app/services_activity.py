"""Activity feed (S5-B-3). Newest first, keyset over (created_at, id). `unread_count` is computed from
`users.activity_last_read_at` on every page (data_model "Derived data"): the number of the caller's entries created
after the read mark (all of them when it is null), ignoring `group_id`, `limit` and `cursor`, and uncapped. An item's
`is_unread` uses the same predicate. Entries whose actor is the caller are never unread (vector 49b);
system entries (actor_id null) are unread for everyone."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import ActivityLog, ActivityRecipient, User
from app.pagination import Key, aware, decode, encode
from app.schemas import BalanceLine, UserPublic
from app.schemas_settlements import ActivityItem, ActivityPage


def unread_count(db: Session, me: User) -> int:
    stmt = (select(func.count()).select_from(ActivityRecipient)
            .join(ActivityLog, ActivityLog.id == ActivityRecipient.activity_id)
            .where(ActivityRecipient.user_id == me.id, ActivityLog.actor_id.is_distinct_from(me.id)))
    if me.activity_last_read_at is not None:
        stmt = stmt.where(ActivityLog.created_at > me.activity_last_read_at)
    return db.scalar(stmt) or 0


def list_activity(db: Session, me: User, limit: int, cursor: str | None, group_id: uuid.UUID | None) -> ActivityPage:
    stmt = (select(ActivityLog, ActivityRecipient.balance_effect)
            .join(ActivityRecipient, ActivityRecipient.activity_id == ActivityLog.id)
            .where(ActivityRecipient.user_id == me.id))
    if group_id is not None:
        stmt = stmt.where(ActivityLog.group_id == group_id)
    if cursor:
        after = decode(cursor, dated=False)
        stmt = stmt.where(or_(ActivityLog.created_at < after.created_at,
                              and_(ActivityLog.created_at == after.created_at, ActivityLog.id < after.id)))
    rows = db.execute(stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    actor_ids = {log.actor_id for log, _ in rows if log.actor_id is not None}
    actors = {u.id: UserPublic.model_validate(u)
              for u in db.scalars(select(User).where(User.id.in_(actor_ids)))} if actor_ids else {}
    mark = aware(me.activity_last_read_at) if me.activity_last_read_at is not None else None
    items = [ActivityItem(
        id=log.id, action=log.action, actor=actors.get(log.actor_id), entity_type=log.entity_type,
        entity_id=log.entity_id, group_id=log.group_id, summary=log.payload,
        my_effect=[BalanceLine(amount_minor=line["amount_minor"], currency=line["currency"])
                   for line in (effect or [])],
        is_unread=log.actor_id != me.id and (mark is None or aware(log.created_at) > mark), created_at=aware(log.created_at))
        for log, effect in rows]
    next_cursor = encode(Key(None, aware(rows[-1][0].created_at), rows[-1][0].id)) if more else None
    return ActivityPage(items=items, next_cursor=next_cursor, unread_count=unread_count(db, me))


def mark_read(db: Session, me: User) -> None:
    me.activity_last_read_at = datetime.now(timezone.utc)
    db.commit()
