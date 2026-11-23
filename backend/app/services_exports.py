"""CSV export jobs (S6-B-7, F-45). `POST /exports` checks premium (402), then access (403), writes a `pending` row and
returns 202; `generate` builds the file in the background and marks it `ready` (or `failed`). Every poll of a ready
export returns a fresh signed URL valid 15 minutes. The file and the row are purged 24 h after creation: a poll after
that purges what is left and answers 404; the scheduler purges the rest."""
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.csv_export import ExportRow, build_csv
from app.errors import ApiError
from app.models import (Category, Currency, Export, Expense, ExpensePayer, ExpenseSplit, Group, GroupMember,
                        Settlement, User)
from app.pagination import aware
from app.schemas_exports import ExportCreate, ExportOut
from app.services_friends import _visible_friend
from app.services_premium import require_premium
from app.storage import get_storage

log = logging.getLogger("app.exports")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "export"


def create_export(db: Session, me: User, req: ExportCreate) -> ExportOut:
    require_premium(me, "export")
    group_id = friend_id = None
    label = ""
    if req.scope == "group":
        if req.group_id is None:
            raise _invalid("group_id", "group_id is required when scope is group")
        group = db.get(Group, req.group_id)
        if group is None:
            raise ApiError(404, "NOT_FOUND", "Group not found")
        row = db.get(GroupMember, (group.id, me.id))
        if row is None or row.left_at is not None:
            raise ApiError(403, "FORBIDDEN", "You are not a member of this group")
        group_id, label = group.id, group.name
    else:
        if req.friend_user_id is None:
            raise _invalid("friend_user_id", "friend_user_id is required when scope is friend")
        friend = _visible_friend(db, me, req.friend_user_id)
        if friend is None:
            raise ApiError(403, "FORBIDDEN", "That person is not your friend")
        friend_id, label = friend.id, friend.name
    now = _now()
    ex = Export(id=uuid.uuid4(), requested_by=me.id, scope=req.scope, group_id=group_id, friend_id=friend_id,
                format="csv", status="pending", file_name=f"{_slug(label)}-{now.date().isoformat()}.csv",
                purge_at=now + timedelta(hours=settings.export_retention_hours), created_at=now)
    db.add(ex)
    db.commit()
    return export_out(ex)


def export_out(ex: Export) -> ExportOut:
    url = expires = None
    if ex.status == "ready" and ex.storage_key:
        now = _now()
        url = get_storage().signed_url(ex.storage_key, settings.export_url_seconds, now.timestamp())
        expires = now + timedelta(seconds=settings.export_url_seconds)
    return ExportOut(id=ex.id, status=ex.status, scope=ex.scope, format=ex.format, download_url=url,
                     file_name=ex.file_name if ex.status == "ready" else None, expires_at=expires,
                     created_at=aware(ex.created_at))


def purge(db: Session, ex: Export) -> None:
    if ex.storage_key:
        get_storage().delete(ex.storage_key)
    db.delete(ex)
    db.commit()


def get_export(db: Session, me: User, export_id: uuid.UUID) -> ExportOut:
    ex = db.get(Export, export_id)
    if ex is None or ex.requested_by != me.id:
        raise ApiError(404, "NOT_FOUND", "Export not found")
    if ex.purge_at is not None and aware(ex.purge_at) <= _now():
        purge(db, ex)
        raise ApiError(404, "NOT_FOUND", "Export not found")
    return export_out(ex)


def purge_expired(db: Session, now: datetime | None = None) -> int:
    now = now or _now()
    rows = db.scalars(select(Export).where(Export.purge_at <= now)).all()
    for ex in rows:
        if ex.storage_key:
            get_storage().delete(ex.storage_key)
        db.delete(ex)
    db.commit()
    return len(rows)


# ---------- building the file ----------
def _rows_for(db: Session, ex: Export) -> tuple[list[tuple[uuid.UUID, str]], list[ExportRow]]:
    me = ex.requested_by
    if ex.scope == "group":
        members = db.execute(select(User.id, User.name).join(GroupMember, GroupMember.user_id == User.id)
                             .where(GroupMember.group_id == ex.group_id).order_by(GroupMember.sort_index)).all()
        exp_where = [Expense.group_id == ex.group_id]
        set_where = [Settlement.group_id == ex.group_id]
    else:
        names = dict(db.execute(select(User.id, User.name).where(User.id.in_([me, ex.friend_id]))).all())
        members = [(me, names[me]), (ex.friend_id, names[ex.friend_id])]
        both = {me, ex.friend_id}
        my_groups = (select(GroupMember.group_id).join(Group, Group.id == GroupMember.group_id)
                     .where(GroupMember.user_id == me, GroupMember.left_at.is_(None), Group.deleted_at.is_(None)))
        involved = [Expense.id.in_(select(ExpensePayer.expense_id).where(ExpensePayer.user_id == u).union(
            select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == u))) for u in both]
        exp_where = [*involved, or_(Expense.group_id.is_(None), Expense.group_id.in_(my_groups))]
        set_where = [or_(and_(Settlement.from_user_id == me, Settlement.to_user_id == ex.friend_id),
                         and_(Settlement.from_user_id == ex.friend_id, Settlement.to_user_id == me)),
                     or_(Settlement.group_id.is_(None), Settlement.group_id.in_(my_groups))]
    members = [(u, n) for u, n in members]
    categories = dict(db.execute(select(Category.id, Category.name)).all())
    out: list[tuple[date, datetime, ExportRow]] = []
    for e in db.scalars(select(Expense).where(*exp_where, Expense.deleted_at.is_(None))):
        nets: dict[uuid.UUID, int] = {}
        for u, paid in db.execute(select(ExpensePayer.user_id, ExpensePayer.paid_amount_minor)
                                  .where(ExpensePayer.expense_id == e.id)):
            nets[u] = nets.get(u, 0) + paid
        for u, owed in db.execute(select(ExpenseSplit.user_id, ExpenseSplit.owed_amount_minor)
                                  .where(ExpenseSplit.expense_id == e.id)):
            nets[u] = nets.get(u, 0) - owed
        out.append((e.expense_date, aware(e.created_at),
                    ExportRow(e.expense_date, e.description, categories.get(e.category_id, ""),
                              e.total_amount_minor, e.currency, nets)))
    names = dict(members)
    for s in db.scalars(select(Settlement).where(*set_where, Settlement.deleted_at.is_(None))):
        label = f"Payment: {names.get(s.from_user_id, '?')} paid {names.get(s.to_user_id, '?')}"
        out.append((s.settled_on, aware(s.created_at),
                    ExportRow(s.settled_on, label, "Payment", s.amount_minor, s.currency,
                              {s.from_user_id: s.amount_minor, s.to_user_id: -s.amount_minor})))
    out.sort(key=lambda t: (t[0], t[1]))
    return members, [r for _, _, r in out]


def generate(db: Session, export_id: uuid.UUID) -> None:
    """Build and store the file for a pending export. Never raises: a failure marks the export `failed`."""
    ex = db.get(Export, export_id)
    if ex is None or ex.status != "pending":
        return
    try:
        members, rows = _rows_for(db, ex)
        exponents = dict(db.execute(select(Currency.code, Currency.exponent)).all())
        text = build_csv(members, rows, exponents)
        key = f"exports/{ex.id}/{ex.file_name}"
        get_storage().put(key, text.encode("utf-8"))
        ex.storage_key, ex.status = key, "ready"
    except Exception:  # noqa: BLE001 - reported through the export status
        log.exception("export %s failed", export_id)
        db.rollback()
        ex = db.get(Export, export_id)
        ex.status = "failed"
    db.commit()


def process_pending(db: Session) -> int:
    ids = list(db.scalars(select(Export.id).where(Export.status == "pending")))
    for i in ids:
        generate(db, i)
    return len(ids)
