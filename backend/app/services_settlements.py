"""Settlements (S5-B-2): record, list, read, edit, delete, restore, settle all.

Money is integer minor units end to end. A settlement `from -> to` of `a` adds `a` to the payer's net and subtracts it
from the receiver's net (business_rules 4); the balance queries in `services_balances` read the live rows.
Authorization:
 - a group settlement is visible to and editable by the group's current members only;
 - a non-group settlement is visible to its two parties only; only a party may record one (403 otherwise).
Check order for edit / delete / restore mirrors expenses (business_rules 8 and 6): unknown id 404, no access 403,
ALREADY_DELETED / NOT_DELETED 409, VERSION_CONFLICT 409, EXPENSE_HAS_DEPARTED_MEMBER 409, then field validation."""
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import activity, idempotency, services_balances
from app.errors import ApiError
from app.models import Currency, Group, GroupMember, Settlement, User
from app.pagination import Key, aware, decode, encode
from app.schemas_expenses import MoneyOut
from app.schemas_settlements import (SettleAllOut, SettleAllRequest, SettlementCreate, SettlementOut,
                                     SettlementPage, SettlementUpdate)
from app.services_friends import _visible_friend, shared_group_ids
from app.services_groups import _live_group_for_member, lock_group
from app.splits import SplitError, validate_total

DEPARTED_MESSAGE = "This payment involves someone who left the group or is no longer a friend"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


def out(s: Settlement) -> SettlementOut:
    return SettlementOut(id=s.id, group_id=s.group_id,
                         from_user_id=s.from_user_id, to_user_id=s.to_user_id,
                         amount=MoneyOut(amount_minor=s.amount_minor, currency=s.currency), settled_on=s.settled_on,
                         note=s.note, batch_id=s.batch_id, created_by=s.created_by, created_at=aware(s.created_at),
                         deleted_at=aware(s.deleted_at) if s.deleted_at else None, version=s.version)


# ---------- access ----------
def _is_active_member(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = db.get(GroupMember, (group_id, user_id))
    return row is not None and row.left_at is None


def _can_access(db: Session, me: User, s: Settlement) -> bool:
    if s.group_id is not None:
        return _is_active_member(db, s.group_id, me.id)
    return me.id in (s.from_user_id, s.to_user_id)


def _load(db: Session, me: User, settlement_id: uuid.UUID, *, reading: bool = False) -> Settlement:
    """404 for an unknown id. Without access: 404 for a read (GET declares no 403 and must not reveal that the id
    exists), 403 for a write."""
    s = db.get(Settlement, settlement_id)
    if s is None:
        raise ApiError(404, "NOT_FOUND", "Payment not found")
    if not _can_access(db, me, s):
        if reading:
            raise ApiError(404, "NOT_FOUND", "Payment not found")
        raise ApiError(403, "FORBIDDEN", "You cannot access this payment")
    return s


def _departed_guard(db: Session, s: Settlement, *, check_friendship: bool) -> None:
    """EXPENSE_HAS_DEPARTED_MEMBER (OQ-43): a group settlement whose payer or receiver left the group; on restore, a
    non-group settlement whose two users are no longer friends."""
    if s.group_id is not None:
        active = set(db.scalars(select(GroupMember.user_id).where(
            GroupMember.group_id == s.group_id, GroupMember.user_id.in_([s.from_user_id, s.to_user_id]),
            GroupMember.left_at.is_(None))))
        departed = {s.from_user_id, s.to_user_id} - active
    elif check_friendship:
        payer = db.get(User, s.from_user_id)
        departed = payer is None or _visible_friend(db, payer, s.to_user_id) is None
    else:
        departed = False
    if departed:
        raise ApiError(409, "EXPENSE_HAS_DEPARTED_MEMBER", DEPARTED_MESSAGE)


# ---------- keyset reading ----------
def settlement_key(s: Settlement) -> Key:
    return Key(s.settled_on, aware(s.created_at), s.id)


def _rows(db: Session, base, after: Key | None, limit: int) -> list[Settlement]:
    stmt = base
    if after is not None:
        stmt = stmt.where(or_(Settlement.settled_on < after.day,
                              and_(Settlement.settled_on == after.day,
                                   or_(Settlement.created_at < after.created_at,
                                       and_(Settlement.created_at == after.created_at, Settlement.id < after.id)))))
    stmt = stmt.order_by(Settlement.settled_on.desc(), Settlement.created_at.desc(), Settlement.id.desc())
    return list(db.scalars(stmt.limit(limit)))


def group_rows(db: Session, group_id: uuid.UUID, include_deleted: bool, after: Key | None,
               limit: int) -> list[Settlement]:
    """The group timeline's settlement source (S5-B-4): up to `limit` rows strictly after `after`."""
    base = select(Settlement).where(Settlement.group_id == group_id)
    if not include_deleted:
        base = base.where(Settlement.deleted_at.is_(None))
    return _rows(db, base, after, limit)


def list_settlements(db: Session, me: User, limit: int, cursor: str | None, group_id: uuid.UUID | None,
                     friend_user_id: uuid.UUID | None) -> SettlementPage:
    """The caller's live settlements: those they are the payer or receiver of, in groups they are still in (or none)."""
    if group_id is not None:
        if db.get(Group, group_id) is None:
            raise ApiError(404, "NOT_FOUND", "Group not found")
        if not _is_active_member(db, group_id, me.id):
            raise ApiError(403, "FORBIDDEN", "You are not a member of this group")
    my_groups = (select(GroupMember.group_id).join(Group, Group.id == GroupMember.group_id)
                 .where(GroupMember.user_id == me.id, GroupMember.left_at.is_(None), Group.deleted_at.is_(None)))
    base = select(Settlement).where(
        Settlement.deleted_at.is_(None), or_(Settlement.from_user_id == me.id, Settlement.to_user_id == me.id),
        or_(Settlement.group_id.is_(None), Settlement.group_id.in_(my_groups)))
    if group_id is not None:
        base = base.where(Settlement.group_id == group_id)
    if friend_user_id is not None:
        base = base.where(or_(Settlement.from_user_id == friend_user_id, Settlement.to_user_id == friend_user_id))
    key = decode(cursor, dated=True) if cursor else None
    rows = _rows(db, base, key, limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    return SettlementPage(items=[out(s) for s in rows], next_cursor=encode(settlement_key(rows[-1])) if more else None)


def get_settlement(db: Session, me: User, settlement_id: uuid.UUID) -> SettlementOut:
    return out(_load(db, me, settlement_id, reading=True))


# ---------- activity ----------
def _log(db: Session, me: User, action: str, s: Settlement, effect: dict[uuid.UUID, int],
         previous_amount: int | None = None) -> None:
    """One activity row for the payer, the receiver and the actor. `effect` is each party's signed balance change."""
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_([s.from_user_id, s.to_user_id])))}
    payload: dict[str, Any] = {
        "amount": {"amount_minor": s.amount_minor, "currency": s.currency},
        "from_user_id": str(s.from_user_id), "from_name": names.get(s.from_user_id),
        "to_user_id": str(s.to_user_id), "to_name": names.get(s.to_user_id), "note": s.note,
        "actor_name": me.name}
    if previous_amount is not None:
        payload["previous_amount"] = {"amount_minor": previous_amount, "currency": s.currency}
    activity.record(db, me.id, action, "settlement", s.id, s.group_id, payload,
                    {s.from_user_id, s.to_user_id, me.id},
                    {u: {s.currency: v} for u, v in effect.items() if v})


def _effect(s: Settlement, amount: int) -> dict[uuid.UUID, int]:
    """Paying raises the payer's net and lowers the receiver's by `amount`."""
    return {s.from_user_id: amount, s.to_user_id: -amount}


# ---------- create ----------
def _today(me: User) -> date:
    try:
        return datetime.now(ZoneInfo(me.time_zone)).date()
    except Exception:  # unknown zone name: fall back to UTC
        return datetime.now(timezone.utc).date()


def _currency(db: Session, code: str) -> str:
    code = code.upper()
    row = db.get(Currency, code)
    if row is None or not row.is_active:
        raise ApiError(422, "CURRENCY_UNKNOWN", f"Unsupported currency {code}",
                       {"fields": [{"field": "amount.currency", "message": "unsupported currency"}]})
    return code


def _amount(minor: int) -> int:
    try:
        validate_total(minor)
    except SplitError:
        raise ApiError(422, "AMOUNT_OUT_OF_RANGE", "The amount must be between 1 and 9,999,999,999 minor units",
                       {"fields": [{"field": "amount.amount_minor", "message": "out of range"}]})
    return minor


def _check_access_and_parties(db: Session, me: User, req: SettlementCreate) -> None:
    if req.group_id is not None:
        lock_group(db, req.group_id)
        _live_group_for_member(db, me, req.group_id)  # 404 unknown, 403 not a member, 409 deleted group
        active = set(db.scalars(select(GroupMember.user_id).where(
            GroupMember.group_id == req.group_id, GroupMember.user_id.in_([req.from_user_id, req.to_user_id]),
            GroupMember.left_at.is_(None))))
        outside = {req.from_user_id, req.to_user_id} - active
        if outside:
            raise ApiError(422, "PARTICIPANT_NOT_MEMBER", "Both people must be members of the group",
                           {"user_ids": sorted(str(u) for u in outside)})
        return
    if me.id not in (req.from_user_id, req.to_user_id):
        raise ApiError(403, "FORBIDDEN", "You can only record a payment you made or received")
    other = req.to_user_id if req.from_user_id == me.id else req.from_user_id
    if _visible_friend(db, me, other) is None:
        raise ApiError(422, "PARTICIPANT_NOT_MEMBER", "The other person must be a friend",
                       {"user_ids": [str(other)]})


def _free_key(db: Session, me: User, key: uuid.UUID | None) -> None:
    if key is not None:
        # An expired (or gone) key row no longer protects the earlier settlement; free the stored key on it, in this
        # same transaction, so the unique (created_by, idempotency_key) constraint admits the new row.
        db.execute(update(Settlement).where(Settlement.created_by == me.id, Settlement.idempotency_key == key)
                   .values(idempotency_key=None))


def _create(db: Session, me: User, req: SettlementCreate, key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    if req.from_user_id == req.to_user_id:
        raise ApiError(422, "SAME_PARTY", "Payer and receiver must be different people",
                       {"fields": [{"field": "to_user_id", "message": "must differ from from_user_id"}]})
    _check_access_and_parties(db, me, req)
    amount = _amount(req.amount.amount_minor)
    currency = _currency(db, req.amount.currency)
    now = _now()
    _free_key(db, me, key)
    s = Settlement(id=uuid.uuid4(), group_id=req.group_id, from_user_id=req.from_user_id, to_user_id=req.to_user_id,
                   amount_minor=amount, currency=currency, settled_on=req.settled_on or _today(me), note=req.note,
                   method="cash", created_by=me.id, idempotency_key=key, version=1, created_at=now, updated_at=now)
    db.add(s)
    db.flush()
    _log(db, me, "settlement.created", s, _effect(s, amount))
    return 201, out(s).model_dump(mode="json")


def create_settlement(db: Session, me: User, req: SettlementCreate, key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    path = "POST /settlements"
    if key is not None:
        hit = idempotency.lookup(db, me.id, key, path)
        if hit is not None:
            return hit
    for attempt in (1, 2):
        try:
            status, body = _create(db, me, req, key)
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


# ---------- settle all ----------
def settle_all(db: Session, me: User, req: SettleAllRequest) -> SettleAllOut:
    """One settlement per (scope, currency) with a non-zero edge between the caller and the friend, each for the exact
    edge amount, all sharing a batch_id (business_rules 6). The debtor of an edge is the payer."""
    friend_id = req.friend_user_id
    if friend_id == me.id:
        raise ApiError(422, "SAME_PARTY", "Payer and receiver must be different people",
                       {"fields": [{"field": "friend_user_id", "message": "must not be you"}]})
    if _visible_friend(db, me, friend_id) is None:
        raise ApiError(422, "PARTICIPANT_NOT_MEMBER", "The other person must be a friend",
                       {"user_ids": [str(friend_id)]})
    currency = _currency(db, req.currency) if req.currency is not None else None
    for gid in sorted(shared_group_ids(db, me.id, friend_id), key=str):  # fixed order: no lock-order deadlocks
        lock_group(db, gid)
    pairs = services_balances.compute_pairs(db, me.id)
    scopes: list[tuple[uuid.UUID | None, dict[str, int]]] = [
        (g.id, dict(mine.get(friend_id, {}))) for g, mine in pairs.groups]
    scopes.append((None, dict(pairs.non_group.get(friend_id, {}))))
    batch_id, now, today = uuid.uuid4(), _now(), _today(me)
    made: list[Settlement] = []
    for group_id, by_currency in scopes:
        for cur in sorted(by_currency):
            amount = by_currency[cur]
            if amount == 0 or (currency is not None and cur != currency):
                continue
            frm, to = (friend_id, me.id) if amount > 0 else (me.id, friend_id)  # positive: the friend owes me
            s = Settlement(id=uuid.uuid4(), group_id=group_id, from_user_id=frm, to_user_id=to,
                           amount_minor=abs(amount), currency=cur, settled_on=today, method="cash",
                           created_by=me.id, batch_id=batch_id, version=1, created_at=now, updated_at=now)
            db.add(s)
            db.flush()
            _log(db, me, "settlement.created", s, _effect(s, s.amount_minor))
            made.append(s)
    db.commit()
    return SettleAllOut(batch_id=batch_id, items=[out(s) for s in made])


# ---------- edit, delete, restore ----------
def _lock_if_group(db: Session, s: Settlement) -> None:
    if s.group_id is not None:
        lock_group(db, s.group_id)
        db.refresh(s)  # the row may have changed while waiting for the lock


def update_settlement(db: Session, me: User, settlement_id: uuid.UUID, req: SettlementUpdate) -> SettlementOut:
    s = _load(db, me, settlement_id)
    _lock_if_group(db, s)
    if s.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The payment has been deleted")
    if req.version != s.version:
        raise ApiError(409, "VERSION_CONFLICT", "The payment was changed by someone else",
                       {"current_version": s.version})
    _departed_guard(db, s, check_friendship=False)
    sent = req.model_fields_set
    values: dict[str, Any] = {}
    if "amount" in sent:
        if req.amount is None:
            raise _invalid("amount", "amount cannot be null")
        if req.amount.currency.upper() != s.currency:
            raise _invalid("amount.currency", "The currency of a payment cannot be changed")
        amount = _amount(req.amount.amount_minor)
        if amount != s.amount_minor:
            values["amount_minor"] = amount
    if "settled_on" in sent:
        if req.settled_on is None:
            raise _invalid("settled_on", "settled_on cannot be null")
        if req.settled_on != s.settled_on:
            values["settled_on"] = req.settled_on
    if "note" in sent and req.note != s.note:
        values["note"] = req.note
    if not values:
        return out(s)  # nothing to change: no version bump, no activity
    old_amount = s.amount_minor
    res = db.execute(update(Settlement).where(Settlement.id == s.id, Settlement.version == req.version,
                                              Settlement.deleted_at.is_(None))
                     .values(**values, version=Settlement.version + 1, updated_at=_now()))
    if res.rowcount != 1:  # lost a race with another edit or a delete
        db.rollback()
        current = db.scalar(select(Settlement.version).where(Settlement.id == settlement_id))
        raise ApiError(409, "VERSION_CONFLICT", "The payment was changed by someone else", {"current_version": current})
    db.refresh(s)
    _log(db, me, "settlement.updated", s, _effect(s, s.amount_minor - old_amount),
         previous_amount=old_amount if s.amount_minor != old_amount else None)
    db.commit()
    db.refresh(s)
    return out(s)


def delete_settlement(db: Session, me: User, settlement_id: uuid.UUID) -> SettlementOut:
    s = _load(db, me, settlement_id)
    if s.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The payment has already been deleted")
    _lock_if_group(db, s)
    if s.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The payment has already been deleted")
    _departed_guard(db, s, check_friendship=False)
    now = _now()
    res = db.execute(update(Settlement).where(Settlement.id == s.id, Settlement.deleted_at.is_(None))
                     .values(deleted_at=now, deleted_by=me.id, version=Settlement.version + 1, updated_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise ApiError(409, "ALREADY_DELETED", "The payment has already been deleted")
    db.refresh(s)
    _log(db, me, "settlement.deleted", s, _effect(s, -s.amount_minor))
    db.commit()
    db.refresh(s)
    return out(s)


def restore_settlement(db: Session, me: User, settlement_id: uuid.UUID) -> SettlementOut:
    s = _load(db, me, settlement_id)
    if s.deleted_at is None:
        raise ApiError(409, "NOT_DELETED", "The payment is not deleted")
    _lock_if_group(db, s)
    if s.deleted_at is None:
        raise ApiError(409, "NOT_DELETED", "The payment is not deleted")
    _departed_guard(db, s, check_friendship=True)
    now = _now()
    res = db.execute(update(Settlement).where(Settlement.id == s.id, Settlement.deleted_at.is_not(None))
                     .values(deleted_at=None, deleted_by=None, version=Settlement.version + 1, updated_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise ApiError(409, "NOT_DELETED", "The payment is not deleted")
    db.refresh(s)
    _log(db, me, "settlement.restored", s, _effect(s, s.amount_minor))
    db.commit()
    db.refresh(s)
    return out(s)
