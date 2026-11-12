"""Groups (S2-B-5). Any active member may read and change a group (no admin role, OQ-10). Group balances are
empty until Slice 4, and the leave/remove balance guard reads 0 until then. When a shared group ends, the pairs
that no longer share any live group become explicit friends (S2-B-8, OQ-37a, business_rules 10.1a)."""
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import case, exists, func, literal, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app import activity, idempotency, outbox, services_balances
from app.errors import ApiError
from app.models import Currency, Friendship, Group, GroupMember, User
from app.schemas import (BalanceLine, GroupCreate, GroupList, GroupMemberOut, GroupOut, GroupSummary, GroupUpdate,
                         MembersAdd, NewMember, UserPublic)
from app.services_auth import NOTIFICATION_KEYS
from app.services_friends import _unused_friend_code

MAX_MEMBERS = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


# ---------- reads ----------
def _active_member_ids(db: Session, group_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(GroupMember.user_id).where(
        GroupMember.group_id == group_id, GroupMember.left_at.is_(None)).order_by(GroupMember.sort_index)))


def _load_for_member(db: Session, me: User, group_id: uuid.UUID) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise ApiError(404, "NOT_FOUND", "Group not found")
    membership = db.get(GroupMember, (group_id, me.id))
    if membership is None or membership.left_at is not None:
        raise ApiError(403, "FORBIDDEN", "You are not a member of this group")
    return group


def _live_group_for_member(db: Session, me: User, group_id: uuid.UUID) -> Group:
    group = _load_for_member(db, me, group_id)
    if group.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The group has been deleted")
    return group


def lock_group(db: Session, group_id: uuid.UUID) -> None:
    """Serialise membership changes and balance-changing expense writes per group (SELECT ... FOR UPDATE on the group
    row; held until the transaction ends). Without it, on READ COMMITTED an expense naming a member could commit
    between the OUTSTANDING_BALANCE read and the leave. SQLite ignores FOR UPDATE (it has one writer anyway)."""
    db.execute(select(Group.id).where(Group.id == group_id).with_for_update())


def member_balances(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> list[BalanceLine]:
    """The member's non-zero nets in the group, per currency (the leave/remove guard, business_rules 8)."""
    return services_balances.user_group_balances(db, user_id, group_id)


# ---------- keep friends when a shared group ends (S2-B-8) ----------
def _keep_friends(db: Session, group_id: uuid.UUID, leaver: uuid.UUID | None) -> None:
    """Upsert explicit friendships (min, max) for candidate pairs that share no other live group, in ONE statement.
    leaver None: every pair of current members of the group (group delete). Otherwise the leaver paired with each
    current member. Writes no activity, recipients, notification or invite rows. Call after the event is flushed."""
    if leaver is None:
        a, b = aliased(GroupMember), aliased(GroupMember)
        pairs = select(a.user_id.label("lo"), b.user_id.label("hi")).where(
            a.group_id == group_id, b.group_id == group_id, a.left_at.is_(None), b.left_at.is_(None),
            a.user_id < b.user_id)
    else:
        y = aliased(GroupMember)
        me = literal(leaver, Friendship.user_id.type)
        pairs = select(case((y.user_id < me, y.user_id), else_=me).label("lo"),
                       case((y.user_id < me, me), else_=y.user_id).label("hi")).where(
            y.group_id == group_id, y.left_at.is_(None), y.user_id != leaver)
    cand = pairs.subquery()
    ma, mb = aliased(GroupMember), aliased(GroupMember)
    still_shared = exists().where(
        ma.user_id == cand.c.lo, mb.user_id == cand.c.hi, ma.group_id == mb.group_id, ma.group_id != group_id,
        ma.left_at.is_(None), mb.left_at.is_(None),
        exists().where(Group.id == ma.group_id, Group.deleted_at.is_(None)).correlate(ma))
    now = _now()
    sel = (select(cand.c.lo, cand.c.hi, literal("active"), literal(now, Friendship.created_at.type),
                  literal(now, Friendship.updated_at.type))
           .where(~still_shared).order_by(cand.c.lo, cand.c.hi))
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(Friendship).from_select(["user_id", "friend_id", "status", "created_at", "updated_at"], sel)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Friendship.user_id, Friendship.friend_id],
        set_={"status": "active", "removed_at": None, "updated_at": now},
        where=Friendship.status == "removed")
    db.execute(stmt)


def group_out(db: Session, group: Group, me: User) -> GroupOut:
    rows = db.execute(
        select(GroupMember, User).join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group.id).order_by(GroupMember.sort_index)
    ).all()
    data = services_balances.load_groups(db, [group.id])[group.id]
    nets = data.nets
    members = [GroupMemberOut(user=UserPublic.model_validate(u), joined_at=m.joined_at, left_at=m.left_at,
                              balances=services_balances.lines({c: n.get(u.id, 0) for c, n in nets.items()}))
               for m, u in rows]
    return GroupOut(
        id=group.id, name=group.name, group_type=group.group_type, simplify_debts=group.simplify_debts,
        default_currency=group.default_currency, avatar_url=group.avatar_url,
        trip_start_date=group.trip_start_date, trip_end_date=group.trip_end_date, whiteboard=group.whiteboard,
        members=members, my_balances=services_balances.member_lines(data, me.id), version=group.version, created_by=group.created_by,
        created_at=group.created_at, deleted_at=group.deleted_at)


def get_group(db: Session, me: User, group_id: uuid.UUID) -> GroupOut:
    return group_out(db, _load_for_member(db, me, group_id), me)


def list_groups(db: Session, me: User) -> GroupList:
    counts = (select(GroupMember.group_id, func.count().label("n")).where(GroupMember.left_at.is_(None))
              .group_by(GroupMember.group_id).subquery())
    rows = db.execute(
        select(Group, counts.c.n)
        .join(GroupMember, (GroupMember.group_id == Group.id) & (GroupMember.user_id == me.id)
              & GroupMember.left_at.is_(None))
        .join(counts, counts.c.group_id == Group.id)
        .where(Group.deleted_at.is_(None)).order_by(Group.updated_at.desc(), Group.id)
    ).all()
    data = services_balances.load_groups(db, [g.id for g, _ in rows])
    items = [GroupSummary(id=g.id, name=g.name, group_type=g.group_type, avatar_url=g.avatar_url, member_count=n,
                          my_balances=services_balances.member_lines(data[g.id], me.id),
                          settled_up_since=data[g.id].settled_up_since(), updated_at=g.updated_at)
             for g, n in rows]
    pairs = services_balances.compute_pairs(db, me.id, with_groups=False)
    return GroupList(items=items, non_group_balances=services_balances.non_group_total(pairs))


# ---------- members ----------
def _check_currency(db: Session, code: str, field: str = "default_currency") -> str:
    code = code.upper()
    if db.get(Currency, code) is None:
        raise _invalid(field, "unknown currency")
    return code


def _existing_for(db: Session, nm: NewMember) -> User | None:
    clauses = []
    if nm.email:
        clauses.append(User.email == nm.email.lower())
    if nm.phone_e164:
        clauses.append(User.phone_e164 == nm.phone_e164)
    if not clauses:
        return None
    return db.scalar(select(User).where(or_(*clauses), User.deleted_at.is_(None)).order_by(User.created_at))


def _create_placeholder(db: Session, me: User, nm: NewMember, group_name: str) -> User:
    user = User(
        email=nm.email.lower() if nm.email else None, phone_e164=nm.phone_e164, name=nm.name,
        is_registered=False, default_currency=me.default_currency, time_zone=me.time_zone,
        notification_prefs={k: True for k in NOTIFICATION_KEYS}, friend_code=_unused_friend_code(db),
        invited_by=me.id)
    db.add(user)
    db.flush()
    if user.email:  # phone-only people are invited through the share sheet (D8)
        outbox.enqueue(db, user.id, "invite", "email",
                       {"to": user.email, "inviter_id": str(me.id), "inviter_name": me.name, "group": group_name})
    return user


def _resolve_people(db: Session, me: User, user_ids: list[uuid.UUID], new_members: list[NewMember],
                    skip: set[uuid.UUID], current_active: int, group_name: str) -> list[User]:
    """Users to add, in order: user_ids, then new_members (found by email/phone, else created as placeholders).
    Anyone in `skip` (already active, or the caller) is ignored. Enforces the 200-member cap before creating."""
    ordered: list[User] = []
    seen = set(skip)
    for uid in user_ids:
        if uid in seen:
            continue
        user = db.get(User, uid)
        if user is None or user.deleted_at is not None:
            raise _invalid("user_ids", f"unknown user {uid}")
        seen.add(uid)
        ordered.append(user)
    pending: list[tuple[int, NewMember]] = []
    slots: list[User | None] = []
    for nm in new_members:
        user = _existing_for(db, nm)
        if user is not None and user.id in seen:
            continue
        if user is not None:
            seen.add(user.id)
        slots.append(user)
        if user is None:
            pending.append((len(slots) - 1, nm))
    if current_active + len(ordered) + len(slots) > MAX_MEMBERS:
        raise ApiError(422, "GROUP_TOO_LARGE", f"A group can have at most {MAX_MEMBERS} members",
                       {"fields": [{"field": "members", "message": f"at most {MAX_MEMBERS} members"}]})
    for idx, nm in pending:
        slots[idx] = _create_placeholder(db, me, nm, group_name)
    return ordered + [u for u in slots if u is not None]


def _add_rows(db: Session, group: Group, users: list[User], start_index: int, added_by: uuid.UUID) -> list[User]:
    """Insert (or reactivate a departed) membership per user, next sort_index values in order."""
    idx = start_index
    for user in users:
        row = db.get(GroupMember, (group.id, user.id))
        if row is None:
            db.add(GroupMember(group_id=group.id, user_id=user.id, role="member", sort_index=idx,
                               added_by=added_by))
        else:
            row.left_at, row.sort_index, row.joined_at, row.added_by = None, idx, _now(), added_by
        idx += 1
    db.flush()
    return users


# ---------- create ----------
def _check_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise ApiError(422, "INVALID_DATE_RANGE", "trip_end_date must not be before trip_start_date",
                       {"fields": [{"field": "trip_end_date", "message": "before trip_start_date"}]})


def _create(db: Session, me: User, req: GroupCreate) -> tuple[int, dict[str, Any]]:
    _check_dates(req.trip_start_date, req.trip_end_date)
    currency = _check_currency(db, req.default_currency) if req.default_currency else me.default_currency
    group = Group(id=uuid.uuid4(), name=req.name, group_type=req.group_type, simplify_debts=req.simplify_debts,
                  default_currency=currency, trip_start_date=req.trip_start_date, trip_end_date=req.trip_end_date,
                  created_by=me.id, version=1)
    others = _resolve_people(db, me, req.member_user_ids, req.new_members, {me.id}, 1, req.name)
    group.created_at = group.updated_at = _now()
    db.add(group)
    db.flush()
    _add_rows(db, group, [me, *others], 0, me.id)
    activity.record(db, me.id, "group.created", "group", group.id, group.id,
                    {"name": group.name, "group_type": group.group_type, "member_count": 1 + len(others)},
                    [me.id, *(u.id for u in others)])
    body = group_out(db, group, me).model_dump(mode="json")
    return 201, body


def create_group(db: Session, me: User, req: GroupCreate, key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    path = "POST /groups"
    if key is not None:
        hit = idempotency.lookup(db, me.id, key, path)
        if hit is not None:
            return hit
    for attempt in (1, 2):
        try:
            status, body = _create(db, me, req)
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


# ---------- update / delete ----------
def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def update_group(db: Session, me: User, group_id: uuid.UUID, req: GroupUpdate) -> GroupOut:
    group = _live_group_for_member(db, me, group_id)
    if req.version != group.version:
        raise ApiError(409, "VERSION_CONFLICT", "The group was changed by someone else",
                       {"current_version": group.version})
    sent = req.model_fields_set - {"version"}
    values: dict[str, Any] = {}
    for field in sent:
        new = getattr(req, field)
        if field == "default_currency":
            new = _check_currency(db, new)
        if getattr(group, field) != new:
            values[field] = new
    _check_dates(values.get("trip_start_date", group.trip_start_date), values.get("trip_end_date", group.trip_end_date))
    if not values:
        return group_out(db, group, me)
    changes = {f: {"from": _jsonable(getattr(group, f)), "to": _jsonable(v)} for f, v in values.items()}
    if "whiteboard" in values:
        values["whiteboard_updated_by"] = me.id
    res = db.execute(update(Group).where(Group.id == group.id, Group.version == req.version,
                                         Group.deleted_at.is_(None))
                     .values(**values, version=Group.version + 1, updated_at=_now()))
    if res.rowcount != 1:  # lost a race
        db.rollback()
        current = db.scalar(select(Group.version).where(Group.id == group_id))
        raise ApiError(409, "VERSION_CONFLICT", "The group was changed by someone else",
                       {"current_version": current})
    db.refresh(group)
    activity.record(db, me.id, "group.updated", "group", group.id, group.id,
                    {"name": group.name, "changes": changes}, _active_member_ids(db, group.id))
    db.commit()
    return group_out(db, group, me)


def delete_group(db: Session, me: User, group_id: uuid.UUID) -> None:
    group = _live_group_for_member(db, me, group_id)
    now = _now()
    res = db.execute(update(Group).where(Group.id == group.id, Group.deleted_at.is_(None))
                     .values(deleted_at=now, deleted_by=me.id, version=Group.version + 1, updated_at=now))
    if res.rowcount != 1:
        db.rollback()
        raise ApiError(409, "ALREADY_DELETED", "The group has already been deleted")
    _keep_friends(db, group.id, None)
    activity.record(db, me.id, "group.deleted", "group", group.id, group.id, {"name": group.name},
                    _active_member_ids(db, group.id))
    db.commit()


# ---------- members ----------
def add_members(db: Session, me: User, group_id: uuid.UUID, req: MembersAdd) -> GroupOut:
    group = _live_group_for_member(db, me, group_id)
    active = set(_active_member_ids(db, group.id))
    next_index = (db.scalar(select(func.max(GroupMember.sort_index)).where(GroupMember.group_id == group.id)) or 0) + 1
    try:
        users = _resolve_people(db, me, req.user_ids, req.new_members, set(active) | {me.id}, len(active), group.name)
        _add_rows(db, group, users, next_index, me.id)
        if users:
            group.updated_at = _now()
            everyone = [*active, *(u.id for u in users)]
            for u in users:
                activity.record(db, me.id, "group.member_added", "group", group.id, group.id,
                                {"name": group.name, "user_id": str(u.id), "user_name": u.name}, everyone)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "VERSION_CONFLICT", "Members changed concurrently, retry")
    return group_out(db, group, me)


def remove_member(db: Session, me: User, group_id: uuid.UUID, user_id_param: str) -> None:
    if user_id_param == "me":
        target_id = me.id
    else:
        try:
            target_id = uuid.UUID(user_id_param)
        except ValueError:
            raise _invalid("user_id", "must be a user id or 'me'")
    lock_group(db, group_id)
    group = _live_group_for_member(db, me, group_id)
    target = db.get(GroupMember, (group.id, target_id))
    if target is None or target.left_at is not None:
        raise ApiError(404, "NOT_FOUND", "Member not found")
    balances = [b for b in member_balances(db, group.id, target_id) if b.amount_minor != 0]
    if balances:
        raise ApiError(409, "OUTSTANDING_BALANCE", "Settle all debts first",
                       {"balances": [b.model_dump() for b in balances]})
    now = _now()
    target.left_at = now
    target.updated_at = now
    group.updated_at = now
    db.flush()
    _keep_friends(db, group.id, target_id)
    user = db.get(User, target_id)
    activity.record(db, me.id, "group.member_removed", "group", group.id, group.id,
                    {"name": group.name, "user_id": str(target_id), "user_name": user.name,
                     "left": target_id == me.id},
                    [*_active_member_ids(db, group.id), target_id])
    db.commit()
