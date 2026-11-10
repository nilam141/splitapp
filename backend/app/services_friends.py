"""Friends: explicit friendships UNION users who share a non-deleted group (derived at read time, OQ-33; no rows
are written for group co-members while the group is live).
Balances are empty until Slice 4."""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import activity, idempotency, outbox, security
from app.errors import ApiError
from app.models import Expense, ExpensePayer, ExpenseSplit, Friendship, Group, GroupMember, User
from app.schemas import Friend, FriendCreate, FriendCreated, UserPublic
from app.services_auth import NOTIFICATION_KEYS

FILTERS = ("all", "outstanding", "owes_me", "i_owe")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """(user_id, friend_id) ordering used by `friendships`: the smaller uuid first."""
    return (a, b) if a < b else (b, a)


def friend_out(user: User) -> Friend:
    return Friend(user=UserPublic.model_validate(user), balances=[], breakdown=[], settled_up_since=None)


def _matches(friend: Friend, mode: str) -> bool:
    amounts = [b.amount_minor for b in friend.balances]
    if mode == "outstanding":
        return any(a != 0 for a in amounts)
    if mode == "owes_me":
        return any(a > 0 for a in amounts)
    if mode == "i_owe":
        return any(a < 0 for a in amounts)
    return True


def _explicit_conditions(me_id: uuid.UUID):
    return (
        User.id.in_(select(Friendship.friend_id).where(Friendship.user_id == me_id, Friendship.status == "active")),
        User.id.in_(select(Friendship.user_id).where(Friendship.friend_id == me_id, Friendship.status == "active")),
    )


def _shared_user_ids(me_id: uuid.UUID):
    """Users who share at least one non-deleted group with me (both memberships current)."""
    mine = GroupMember.__table__.alias("mine")
    theirs = GroupMember.__table__.alias("theirs")
    return (
        select(theirs.c.user_id.label("uid"))
        .select_from(mine.join(theirs, theirs.c.group_id == mine.c.group_id)
                     .join(Group, Group.id == mine.c.group_id))
        .where(mine.c.user_id == me_id, mine.c.left_at.is_(None), theirs.c.left_at.is_(None),
               theirs.c.user_id != me_id, Group.deleted_at.is_(None))
    )


def shared_group_ids(db: Session, a: uuid.UUID, b: uuid.UUID) -> list[uuid.UUID]:
    """Non-deleted groups both users are currently in, oldest first."""
    ma = GroupMember.__table__.alias("ma")
    mb = GroupMember.__table__.alias("mb")
    rows = db.execute(
        select(Group.id).select_from(ma.join(mb, mb.c.group_id == ma.c.group_id).join(Group, Group.id == ma.c.group_id))
        .where(ma.c.user_id == a, mb.c.user_id == b, ma.c.left_at.is_(None), mb.c.left_at.is_(None),
               Group.deleted_at.is_(None))
        .order_by(Group.created_at, Group.id)
    ).scalars().all()
    return list(rows)


def list_friends(db: Session, me: User, mode: str) -> list[Friend]:
    rows = db.scalars(
        select(User).where(or_(*_explicit_conditions(me.id), User.id.in_(_shared_user_ids(me.id))),
                           User.deleted_at.is_(None), User.id != me.id)
        .order_by(User.name, User.id)
    ).all()
    return [f for f in (friend_out(u) for u in rows) if _matches(f, mode)]


def _explicit_active(db: Session, me: User, other_id: uuid.UUID) -> bool:
    a, b = pair(me.id, other_id)
    row = db.get(Friendship, (a, b))
    return row is not None and row.status == "active"


def _visible_friend(db: Session, me: User, other_id: uuid.UUID) -> User | None:
    """The other user if they are in my derived friend list (explicit active row or a shared live group)."""
    if other_id == me.id:
        return None
    user = db.get(User, other_id)
    if user is None or user.deleted_at is not None:
        return None
    if _explicit_active(db, me, other_id) or shared_group_ids(db, me.id, other_id):
        return user
    return None


def get_friend(db: Session, me: User, other_id: uuid.UUID) -> Friend:
    user = _visible_friend(db, me, other_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "Friend not found")
    return friend_out(user)


def _soft_delete_pair_expenses(db: Session, a: uuid.UUID, b: uuid.UUID, actor: uuid.UUID, now: datetime) -> None:
    """Soft-delete every live non-group expense whose payers and participants are exactly {a, b} (OQ-32): both are on
    it and nobody else is. Group expenses and expenses with a third person are untouched."""
    inv = union(select(ExpensePayer.expense_id.label("expense_id"), ExpensePayer.user_id.label("user_id")),
                select(ExpenseSplit.expense_id, ExpenseSplit.user_id)).subquery()
    ids = select(Expense.id).where(
        Expense.group_id.is_(None), Expense.deleted_at.is_(None),
        Expense.id.in_(select(inv.c.expense_id).where(inv.c.user_id == a)),
        Expense.id.in_(select(inv.c.expense_id).where(inv.c.user_id == b)),
        Expense.id.not_in(select(inv.c.expense_id).where(inv.c.user_id.not_in([a, b]))))
    db.execute(update(Expense).where(Expense.id.in_(ids)).values(
        deleted_at=now, deleted_by=actor, version=Expense.version + 1, updated_at=now))


def remove_friend(db: Session, me: User, other_id: uuid.UUID) -> None:
    """business_rules 10.2: a shared live group blocks removal (409, even with an explicit row); otherwise the
    explicit row becomes removed and the pair's non-group expenses are soft-deleted in the same transaction,
    whatever the balance (OQ-32). Non-group settlements follow with S5-B-4."""
    if other_id == me.id:
        raise ApiError(404, "NOT_FOUND", "Friend not found")
    shared = shared_group_ids(db, me.id, other_id)
    if shared:
        raise ApiError(409, "SHARED_GROUPS_EXIST", "Remove each other from shared groups first",
                       {"group_ids": [str(g) for g in shared]})
    other = db.get(User, other_id)
    if other is None or other.deleted_at is not None or not _explicit_active(db, me, other_id):
        raise ApiError(404, "NOT_FOUND", "Friend not found")
    row = db.get(Friendship, pair(me.id, other_id))
    now = _now()
    row.status = "removed"
    row.removed_at = now
    row.updated_at = now
    _soft_delete_pair_expenses(db, me.id, other_id, me.id, now)
    activity.record(db, me.id, "friend.removed", "friendship", other_id, None,
                    {"friend_id": str(other_id), "friend_name": other.name, "actor_name": me.name},
                    [me.id, other_id])
    db.commit()


def _unused_friend_code(db: Session) -> str:
    for _ in range(10):
        code = security.new_friend_code()
        if db.scalar(select(User.id).where(User.friend_code == code)) is None:
            return code
    raise RuntimeError("could not generate a unique friend code")


def _find_target(db: Session, req: FriendCreate) -> User | None:
    if req.email is not None:
        return db.scalar(select(User).where(User.email == req.email.lower()))
    if req.phone_e164 is not None:
        return db.scalar(select(User).where(User.phone_e164 == req.phone_e164))
    user = db.scalar(select(User).where(User.friend_code == (req.friend_code or "").strip().upper()))
    if user is None or user.deleted_at is not None:
        raise ApiError(410, "LINK_EXPIRED", "This friend code is not valid")
    return user


def _create_placeholder(db: Session, me: User, req: FriendCreate) -> User:
    if req.name is None:
        raise ApiError(422, "VALIDATION_ERROR", "name is required when the person is not registered",
                       {"fields": [{"field": "name", "message": "required for an unregistered person"}]})
    user = User(
        email=req.email.lower() if req.email else None,
        phone_e164=req.phone_e164,
        name=req.name,
        is_registered=False,
        default_currency=me.default_currency,
        time_zone=me.time_zone,
        notification_prefs={k: True for k in NOTIFICATION_KEYS},
        friend_code=_unused_friend_code(db),
        invited_by=me.id,
    )
    db.add(user)
    db.flush()
    if user.email:  # phone-only invites go through the share sheet (D8); there is no SMS channel to queue
        outbox.enqueue(db, user.id, "invite", "email",
                       {"to": user.email, "inviter_id": str(me.id), "inviter_name": me.name})
    return user


def _add(db: Session, me: User, req: FriendCreate) -> tuple[int, dict[str, Any]]:
    target = _find_target(db, req)
    if target is not None and target.id == me.id:
        raise ApiError(422, "CANNOT_FRIEND_SELF", "You cannot add yourself as a friend")
    is_new = False
    if target is None:
        target = _create_placeholder(db, me, req)
        is_new = True
    a, b = pair(me.id, target.id)
    row = db.get(Friendship, (a, b))
    status = 201
    if row is None:
        db.add(Friendship(user_id=a, friend_id=b, status="active"))
    elif row.status == "active":
        status = 200
    elif row.status == "removed":
        row.status, row.removed_at, row.updated_at = "active", None, _now()
    else:
        raise ApiError(422, "VALIDATION_ERROR", "This person cannot be added as a friend")
    db.flush()
    if status == 201:
        activity.record(db, me.id, "friend.added", "friendship", target.id, None,
                        {"friend_id": str(target.id), "friend_name": target.name, "actor_name": me.name},
                        [me.id, target.id])
    body = FriendCreated(friend=friend_out(target), is_new_user=is_new).model_dump(mode="json")
    return status, body


def add_friend(db: Session, me: User, req: FriendCreate, key: uuid.UUID | None) -> tuple[int, dict[str, Any]]:
    path = "POST /friends"
    if key is not None:
        hit = idempotency.lookup(db, me.id, key, path)
        if hit is not None:
            return hit
    for attempt in (1, 2):
        try:
            status, body = _add(db, me, req)
            if key is not None:
                idempotency.store(db, me.id, key, path, status, body)
            db.commit()
            return status, body
        except IntegrityError as exc:
            db.rollback()
            if key is not None:  # lost a race with the same key: replay the winner
                hit = idempotency.lookup(db, me.id, key, path)
                if hit is not None:
                    return hit
            if attempt == 2:
                raise
            # lost a race on the placeholder email/phone or the friendship row; retry once with fresh reads
    raise AssertionError("unreachable")
