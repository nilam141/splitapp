"""Expenses (S3-B-3, S3-B-4): create, read, list, edit, delete, restore.

Money is integer minor units end to end; all split arithmetic is in `app.splits` (pure). Authorization:
 - a group expense is visible to and editable by the group's current members only (403 otherwise);
 - a non-group expense is visible to and editable by the users who are a payer or a participant of it.
Edits follow `ExpenseUpdate`: only the fields sent change. If `total` changes and `payers` is not sent, a single payer
is re-scaled to the new total; every other stored payer set and every stored split is re-validated against the new total
(equal, percent, shares and adjustment re-compute from their inputs; an exact split or a multi-payer set that no longer
adds up is a 422 SPLIT_SUM_MISMATCH / PAYER_SUM_MISMATCH and the client must resend it)."""
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import idempotency
from app.errors import ApiError
from app.models import (Category, Comment, Currency, Expense, ExpensePayer, ExpenseSplit, Group, GroupMember, User)
from app.pagination import Key, aware, decode, encode
from app.schemas import UserPublic
from app.schemas_expenses import (CommentCreate, CommentOut, CommentPage, ExpenseCreate, ExpenseOut, ExpensePage,
                                  ExpensePayerOut, ExpenseSplitOut, ExpenseUpdate, MoneyOut)
from app.services_friends import _visible_friend
from app.services_groups import _live_group_for_member, _load_for_member
from app.splits import SplitError, compute_split, validate_payers, validate_total

_MESSAGES = {
    "AMOUNT_OUT_OF_RANGE": "The amount must be between 1 and 9,999,999,999 minor units",
    "SPLIT_NO_PARTICIPANTS": "Select at least 1 person to split with",
    "SPLIT_SUM_MISMATCH": "The split does not add up to the total",
    "SPLIT_PERCENT_MISMATCH": "The percentages must add up to 100%",
    "SPLIT_NO_SHARES": "Assign at least 1 share",
    "SPLIT_ADJUSTMENT_EXCEEDS_TOTAL": "The adjustments cannot exceed the total",
    "PAYER_SUM_MISMATCH": "The paid amounts do not add up to the total",
    "DUPLICATE_PAYER": "A person can only be listed once as a payer",
    "DUPLICATE_PARTICIPANT": "A person can only be listed once in the split",
    "VALIDATION_ERROR": "Request validation failed",
}

Payers = list[tuple[uuid.UUID, int]]
SplitRows = list[tuple[uuid.UUID, int, int | None, int]]  # (user_id, owed, input_value, sort_index)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


def _split_error(err: SplitError) -> ApiError:
    return ApiError(422, err.code, _MESSAGES.get(err.code, "Invalid expense"), err.details)


# ---------- reading rows ----------
def _involved_ids():
    """(expense_id, user_id) for every payer and participant."""
    return union(select(ExpensePayer.expense_id.label("expense_id"), ExpensePayer.user_id.label("user_id")),
                 select(ExpenseSplit.expense_id, ExpenseSplit.user_id)).subquery()


def _involving(user_id: uuid.UUID):
    inv = _involved_ids()
    return select(inv.c.expense_id).where(inv.c.user_id == user_id)


def _payers_of(db: Session, expense_id: uuid.UUID) -> Payers:
    rows = db.execute(select(ExpensePayer.user_id, ExpensePayer.paid_amount_minor)
                      .where(ExpensePayer.expense_id == expense_id)).all()
    return sorted(((r[0], r[1]) for r in rows), key=lambda p: str(p[0]))


def _splits_of(db: Session, expense_id: uuid.UUID) -> SplitRows:
    rows = db.execute(select(ExpenseSplit.user_id, ExpenseSplit.owed_amount_minor, ExpenseSplit.input_value,
                             ExpenseSplit.sort_index).where(ExpenseSplit.expense_id == expense_id)
                      .order_by(ExpenseSplit.sort_index)).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def _outs(db: Session, expenses: list[Expense], viewer_id: uuid.UUID) -> list[ExpenseOut]:
    """Full `Expense` objects for the viewer, loading payers, splits and comment counts in three queries."""
    if not expenses:
        return []
    ids = [e.id for e in expenses]
    payers: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = {i: [] for i in ids}
    for eid, uid, amount in db.execute(select(ExpensePayer.expense_id, ExpensePayer.user_id,
                                              ExpensePayer.paid_amount_minor).where(ExpensePayer.expense_id.in_(ids))):
        payers[eid].append((uid, amount))
    splits: dict[uuid.UUID, list[tuple[uuid.UUID, int, int | None]]] = {i: [] for i in ids}
    for eid, uid, owed, value, _ in db.execute(
            select(ExpenseSplit.expense_id, ExpenseSplit.user_id, ExpenseSplit.owed_amount_minor,
                   ExpenseSplit.input_value, ExpenseSplit.sort_index).where(ExpenseSplit.expense_id.in_(ids))
            .order_by(ExpenseSplit.sort_index)):
        splits[eid].append((uid, owed, value))
    counts = dict(db.execute(select(Comment.expense_id, func.count()).where(
        Comment.expense_id.in_(ids), Comment.deleted_at.is_(None)).group_by(Comment.expense_id)).all())
    out = []
    for e in expenses:
        paid = sum(a for u, a in payers[e.id] if u == viewer_id)
        owed = sum(o for u, o, _ in splits[e.id] if u == viewer_id)
        out.append(ExpenseOut(
            id=e.id, group_id=e.group_id, description=e.description,
            total=MoneyOut(amount_minor=e.total_amount_minor, currency=e.currency), category_id=e.category_id,
            expense_date=e.expense_date, notes=e.notes, split_type=e.split_type,
            payers=[ExpensePayerOut(user_id=u, paid_amount_minor=a)
                    for u, a in sorted(payers[e.id], key=lambda p: (-p[1], str(p[0])))],
            splits=[ExpenseSplitOut(user_id=u, owed_amount_minor=o, input_value=v) for u, o, v in splits[e.id]],
            my_net=MoneyOut(amount_minor=paid - owed, currency=e.currency), receipt_url=None,
            recurring_rule_id=e.recurring_rule_id, comment_count=counts.get(e.id, 0), created_by=e.created_by,
            updated_by=e.updated_by, created_at=aware(e.created_at), updated_at=aware(e.updated_at),
            deleted_at=aware(e.deleted_at) if e.deleted_at else None, deleted_by=e.deleted_by, version=e.version))
    return out


def expense_out(db: Session, e: Expense, viewer_id: uuid.UUID) -> ExpenseOut:
    return _outs(db, [e], viewer_id)[0]


# ---------- access ----------
def _is_active_member(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = db.get(GroupMember, (group_id, user_id))
    return row is not None and row.left_at is None


def _load_visible(db: Session, me: User, expense_id: uuid.UUID) -> Expense:
    """404 for an unknown id, 403 when the caller may not see it (not a current group member / not a participant)."""
    e = db.get(Expense, expense_id)
    if e is None:
        raise ApiError(404, "NOT_FOUND", "Expense not found")
    if e.group_id is not None:
        allowed = _is_active_member(db, e.group_id, me.id)
    else:
        allowed = _is_participant(db, e.id, me.id)
    if not allowed:
        raise ApiError(403, "FORBIDDEN", "You cannot access this expense")
    return e


def _is_participant(db: Session, expense_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    paid = db.scalar(select(func.count()).select_from(ExpensePayer).where(
        ExpensePayer.expense_id == expense_id, ExpensePayer.user_id == user_id))
    owed = db.scalar(select(func.count()).select_from(ExpenseSplit).where(
        ExpenseSplit.expense_id == expense_id, ExpenseSplit.user_id == user_id))
    return bool(paid or owed)


# ---------- validation shared by create and edit ----------
def _currency(db: Session, code: str) -> str:
    code = code.upper()
    row = db.get(Currency, code)
    if row is None or not row.is_active:
        raise ApiError(422, "CURRENCY_UNKNOWN", f"Unsupported currency {code}",
                       {"fields": [{"field": "total.currency", "message": "unsupported currency"}]})
    return code


def _check_category(db: Session, category_id: int) -> None:
    if db.get(Category, category_id) is None:
        raise _invalid("category_id", "unknown category")


def _resolve(db: Session, editor: User, created_by: uuid.UUID, group_id: uuid.UUID | None, total: int,
             payers: Payers, split_type: str, entries: list[tuple[uuid.UUID, int | None]],
             known: set[uuid.UUID]) -> tuple[Payers, SplitRows]:
    """Membership checks, then the pure engine. `known` are users already on the stored expense (edit only): they
    are not re-checked against the friend list. Returns the payers and the split rows in canonical order."""
    involved = {u for u, _ in payers} | {u for u, _ in entries}
    order: dict[uuid.UUID, int] | None = None
    if group_id is not None:
        order = {r[0]: r[1] for r in db.execute(select(GroupMember.user_id, GroupMember.sort_index).where(
            GroupMember.group_id == group_id, GroupMember.left_at.is_(None)))}
        outside = involved - set(order)
        if outside:
            raise ApiError(422, "PARTICIPANT_NOT_MEMBER", "Everyone on the expense must be a member of the group",
                           {"user_ids": sorted(str(u) for u in outside)})
    else:
        if created_by not in involved:
            raise ApiError(422, "CURRENT_USER_NOT_INVOLVED", "The expense creator must pay or share in it")
        strangers = [u for u in sorted(involved - {editor.id} - known, key=str)
                     if _visible_friend(db, editor, u) is None]
        if strangers:
            raise ApiError(422, "PARTICIPANT_NOT_MEMBER", "Everyone on a non-group expense must be you or a friend",
                           {"user_ids": [str(u) for u in strangers]})
    try:
        validate_payers(total, payers)
        if order is not None:
            ordered = sorted(entries, key=lambda e: order[e[0]])
        else:
            ordered = sorted(entries, key=lambda e: (e[0] != created_by, str(e[0])))
        owed = compute_split(split_type, total, ordered)
    except SplitError as err:
        raise _split_error(err)
    rows: SplitRows = [(u, owed[u], None if split_type == "equal" else v, i) for i, (u, v) in enumerate(ordered)]
    return payers, rows


def _write_rows(db: Session, expense_id: uuid.UUID, payers: Payers, rows: SplitRows) -> None:
    db.add_all(ExpensePayer(expense_id=expense_id, user_id=u, paid_amount_minor=a) for u, a in payers)
    db.add_all(ExpenseSplit(expense_id=expense_id, user_id=u, owed_amount_minor=o, input_value=v, sort_index=i)
               for u, o, v, i in rows)
    db.flush()


# ---------- create ----------
def _create(db: Session, me: User, req: ExpenseCreate, group_id: uuid.UUID | None,
            key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    if group_id is not None:
        _live_group_for_member(db, me, group_id)
    if req.recurrence is not None:
        raise ApiError(501, "NOT_IMPLEMENTED", "Recurring expenses are not available yet")
    total = req.total.amount_minor
    try:
        validate_total(total)
    except SplitError as err:
        raise _split_error(err)
    currency = _currency(db, req.total.currency)
    _check_category(db, req.category_id)
    payers = [(p.user_id, p.paid_amount_minor) for p in req.payers]
    entries = [(s.user_id, s.value) for s in req.split.entries]
    payers, rows = _resolve(db, me, me.id, group_id, total, payers, req.split.type, entries, set())
    now = _now()
    if key is not None:
        # A key row that has expired (or is gone) no longer protects the earlier expense; free the stored key on it,
        # in this same transaction, so the unique (created_by, idempotency_key) constraint admits the new row.
        db.execute(update(Expense).where(Expense.created_by == me.id, Expense.idempotency_key == key)
                   .values(idempotency_key=None))
    e = Expense(id=uuid.uuid4(), group_id=group_id, description=req.description, total_amount_minor=total,
                currency=currency, category_id=req.category_id, notes=req.notes, expense_date=req.expense_date,
                split_type=req.split.type, created_by=me.id, idempotency_key=key, version=1, created_at=now,
                updated_at=now)
    db.add(e)
    db.flush()
    _write_rows(db, e.id, payers, rows)
    return 201, expense_out(db, e, me.id).model_dump(mode="json")


def create_expense(db: Session, me: User, req: ExpenseCreate, path_group_id: uuid.UUID | None,
                   key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    """`path_group_id` is set for POST /groups/{id}/expenses (the path wins over a body group_id)."""
    group_id = path_group_id if path_group_id is not None else req.group_id
    path = f"POST /groups/{path_group_id}/expenses" if path_group_id is not None else "POST /expenses"
    if key is not None:
        hit = idempotency.lookup(db, me.id, key, path)
        if hit is not None:
            return hit
    for attempt in (1, 2):
        try:
            status, body = _create(db, me, req, group_id, key)
            if key is not None:
                idempotency.store(db, me.id, key, path, status, body)
            db.commit()
            return status, body
        except IntegrityError:
            db.rollback()
            if key is not None:
                hit = idempotency.lookup(db, me.id, key, path)
                if hit is not None:
                    return hit
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


# ---------- read ----------
def get_expense(db: Session, me: User, expense_id: uuid.UUID) -> ExpenseOut:
    return expense_out(db, _load_visible(db, me, expense_id), me.id)


def _after(stmt, key: Key | None):
    """Keyset: rows strictly after `key` in (expense_date, created_at, id) descending order."""
    if key is None:
        return stmt
    return stmt.where(or_(Expense.expense_date < key.day,
                          and_(Expense.expense_date == key.day,
                               or_(Expense.created_at < key.created_at,
                                   and_(Expense.created_at == key.created_at, Expense.id < key.id)))))


def expense_key(e: Expense) -> Key:
    return Key(e.expense_date, aware(e.created_at), e.id)


def expense_rows(db: Session, base, key: Key | None, limit: int) -> list[Expense]:
    """Up to `limit` expenses matching `base`, newest first, strictly after `key`."""
    stmt = _after(base, key).order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.desc())
    return list(db.scalars(stmt.limit(limit)))


def _page(db: Session, me: User, base, limit: int, cursor: str | None) -> ExpensePage:
    key = decode(cursor, dated=True) if cursor else None
    rows = expense_rows(db, base, key, limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    return ExpensePage(items=_outs(db, rows, me.id), next_cursor=encode(expense_key(rows[-1])) if more else None)


def list_group_expenses(db: Session, me: User, group_id: uuid.UUID, limit: int, cursor: str | None,
                        include_deleted: bool) -> ExpensePage:
    _load_for_member(db, me, group_id)
    base = select(Expense).where(Expense.group_id == group_id)
    if not include_deleted:
        base = base.where(Expense.deleted_at.is_(None))
    return _page(db, me, base, limit, cursor)


def list_expenses(db: Session, me: User, limit: int, cursor: str | None, friend_user_id: uuid.UUID | None,
                  non_group: bool | None) -> ExpensePage:
    """The caller's live expenses: those of the live groups they are in, plus non-group expenses they take part in."""
    my_groups = (select(GroupMember.group_id).join(Group, Group.id == GroupMember.group_id)
                 .where(GroupMember.user_id == me.id, GroupMember.left_at.is_(None), Group.deleted_at.is_(None)))
    base = select(Expense).where(
        Expense.deleted_at.is_(None),
        or_(Expense.group_id.in_(my_groups), and_(Expense.group_id.is_(None), Expense.id.in_(_involving(me.id)))))
    if friend_user_id is not None:
        base = base.where(Expense.id.in_(_involving(friend_user_id)), Expense.id.in_(_involving(me.id)))
    if non_group is True:
        base = base.where(Expense.group_id.is_(None))
    elif non_group is False:
        base = base.where(Expense.group_id.is_not(None))
    return _page(db, me, base, limit, cursor)


# ---------- edit ----------
def _format_minor(amount: int, exponent: int) -> str:
    """Integer-only display of minor units: 12000 with exponent 2 -> '120.00'."""
    if exponent == 0:
        return str(amount)
    whole, frac = divmod(amount, 10 ** exponent)
    return f"{whole}.{frac:0{exponent}d}"


def _has_departed(db: Session, e: Expense, users: set[uuid.UUID]) -> bool:
    if e.group_id is None:
        return False
    active = set(db.scalars(select(GroupMember.user_id).where(
        GroupMember.group_id == e.group_id, GroupMember.user_id.in_(users), GroupMember.left_at.is_(None))))
    return bool(users - active)


def update_expense(db: Session, me: User, expense_id: uuid.UUID, req: ExpenseUpdate) -> ExpenseOut:
    e = _load_visible(db, me, expense_id)
    if e.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The expense has been deleted")
    if req.version != e.version:
        raise ApiError(409, "VERSION_CONFLICT", "The expense was changed by someone else",
                       {"current_version": e.version})
    stored_payers = _payers_of(db, e.id)
    stored_rows = _splits_of(db, e.id)
    known = {u for u, _ in stored_payers} | {r[0] for r in stored_rows}
    if _has_departed(db, e, known):
        raise ApiError(409, "EXPENSE_HAS_DEPARTED_MEMBER",
                       "This expense involves someone who left the group and can no longer be edited")
    old_total = e.total_amount_minor  # the ORM row is updated in place by the UPDATE below
    sent = req.model_fields_set
    if "total" in sent:
        if req.total.currency.upper() != e.currency:
            raise _invalid("total.currency", "The currency of an expense cannot be changed")
        total = req.total.amount_minor
        try:
            validate_total(total)
        except SplitError as err:
            raise _split_error(err)
    else:
        total = e.total_amount_minor
    if "category_id" in sent:
        _check_category(db, req.category_id)

    if "payers" in sent:
        payers: Payers = [(p.user_id, p.paid_amount_minor) for p in req.payers]
    elif len(stored_payers) == 1 and total != old_total:
        payers = [(stored_payers[0][0], total)]  # a single payer always pays the whole total
    else:
        payers = stored_payers
    if "split" in sent:
        split_type = req.split.type
        entries: list[tuple[uuid.UUID, int | None]] = [(s.user_id, s.value) for s in req.split.entries]
    else:
        split_type = e.split_type
        entries = [(u, v) for u, _, v, _ in stored_rows]
    payers, rows = _resolve(db, me, e.created_by, e.group_id, total, payers, split_type, entries, known)

    values: dict[str, Any] = {}
    for field, new in (("description", req.description), ("category_id", req.category_id),
                       ("expense_date", req.expense_date)):
        if field in sent and getattr(e, field) != new:
            values[field] = new
    if "notes" in sent and e.notes != req.notes:
        values["notes"] = req.notes
    if total != old_total:
        values["total_amount_minor"] = total
    if split_type != e.split_type:
        values["split_type"] = split_type
    rows_changed = sorted(payers, key=lambda p: str(p[0])) != stored_payers or rows != stored_rows
    if not values and not rows_changed:
        return expense_out(db, e, me.id)  # nothing to change: no version bump, no comment

    now = _now()
    res = db.execute(update(Expense).where(Expense.id == e.id, Expense.version == req.version,
                                           Expense.deleted_at.is_(None))
                     .values(**values, updated_by=me.id, updated_at=now, version=Expense.version + 1))
    if res.rowcount != 1:  # lost a race with another edit or a delete
        db.rollback()
        current = db.scalar(select(Expense.version).where(Expense.id == expense_id))
        raise ApiError(409, "VERSION_CONFLICT", "The expense was changed by someone else",
                       {"current_version": current})
    if rows_changed:
        db.execute(delete(ExpensePayer).where(ExpensePayer.expense_id == e.id))
        db.execute(delete(ExpenseSplit).where(ExpenseSplit.expense_id == e.id))
        _write_rows(db, e.id, payers, rows)
    if "total_amount_minor" in values:
        exponent = db.get(Currency, e.currency).exponent
        db.add(Comment(id=uuid.uuid4(), expense_id=e.id, user_id=None, kind="system", created_at=now, updated_at=now,
                       body=f"total {_format_minor(old_total, exponent)} → "
                            f"{_format_minor(total, exponent)}"))
    db.commit()
    db.refresh(e)
    return expense_out(db, e, me.id)


def delete_expense(db: Session, me: User, expense_id: uuid.UUID) -> ExpenseOut:
    e = _load_visible(db, me, expense_id)
    if e.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The expense has already been deleted")
    now = _now()
    res = db.execute(update(Expense).where(Expense.id == e.id, Expense.deleted_at.is_(None))
                     .values(deleted_at=now, deleted_by=me.id, version=Expense.version + 1, updated_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise ApiError(409, "ALREADY_DELETED", "The expense has already been deleted")
    db.commit()
    db.refresh(e)
    return expense_out(db, e, me.id)


def restore_expense(db: Session, me: User, expense_id: uuid.UUID) -> ExpenseOut:
    e = _load_visible(db, me, expense_id)
    if e.deleted_at is None:
        raise ApiError(409, "NOT_DELETED", "The expense is not deleted")
    now = _now()
    res = db.execute(update(Expense).where(Expense.id == e.id, Expense.deleted_at.is_not(None))
                     .values(deleted_at=None, deleted_by=None, version=Expense.version + 1, updated_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise ApiError(409, "NOT_DELETED", "The expense is not deleted")
    db.commit()
    db.refresh(e)
    return expense_out(db, e, me.id)


# ---------- comments (S3-B-5) ----------
def _comment_out(c: Comment, author: User | None) -> CommentOut:
    return CommentOut(id=c.id, kind=c.kind, user=UserPublic.model_validate(author) if author else None, body=c.body,
                      created_at=aware(c.created_at))


def list_comments(db: Session, me: User, expense_id: uuid.UUID, limit: int, cursor: str | None) -> CommentPage:
    """Oldest first, keyset over (created_at, id) ascending."""
    _load_visible(db, me, expense_id)
    key = decode(cursor, dated=False) if cursor else None
    stmt = (select(Comment, User).outerjoin(User, User.id == Comment.user_id)
            .where(Comment.expense_id == expense_id, Comment.deleted_at.is_(None)))
    if key is not None:
        stmt = stmt.where(or_(Comment.created_at > key.created_at,
                              and_(Comment.created_at == key.created_at, Comment.id > key.id)))
    rows = db.execute(stmt.order_by(Comment.created_at, Comment.id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode(Key(None, aware(rows[-1][0].created_at), rows[-1][0].id)) if more else None
    return CommentPage(items=[_comment_out(c, u) for c, u in rows], next_cursor=next_cursor)


def create_comment(db: Session, me: User, expense_id: uuid.UUID, req: CommentCreate) -> CommentOut:
    e = _load_visible(db, me, expense_id)
    if e.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "Restore the expense to add a comment")
    now = _now()
    c = Comment(id=uuid.uuid4(), expense_id=e.id, user_id=me.id, kind="user", body=req.body, created_at=now,
                updated_at=now)
    db.add(c)
    db.commit()
    return _comment_out(c, me)
