"""Group invite links and joining (S6-B-4). Any current member may read or reset the link. Joining with a token adds
the caller as a member (or reactivates them) and can claim a placeholder member's history (business_rules 8 "Placeholder
merge"): every row that points at the placeholder is re-pointed to the joining user in the same transaction."""
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import activity
from app.config import settings
from app.errors import ApiError
from app.models import (ActivityLog, Comment, Expense, ExpensePayer, ExpenseSplit, Friendship, Group, GroupInvite,
                        GroupMember, Settlement, User)
from app.schemas import GroupOut, InviteLink, JoinGroupRequest
from app.services_friends import pair
from app.services_groups import (MAX_MEMBERS, _active_member_ids, _live_group_for_member, group_out, lock_group)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _link(inv: GroupInvite) -> InviteLink:
    return InviteLink(token=inv.token, url=settings.invite_base_url.rstrip("/") + "/" + inv.token)


def _active_invite(db: Session, group_id: uuid.UUID) -> GroupInvite | None:
    return db.scalar(select(GroupInvite).where(GroupInvite.group_id == group_id, GroupInvite.revoked_at.is_(None)))


def _new_invite(db: Session, group_id: uuid.UUID, by: uuid.UUID) -> GroupInvite:
    inv = GroupInvite(id=uuid.uuid4(), group_id=group_id, token=secrets.token_urlsafe(9), created_by=by)
    db.add(inv)
    db.flush()
    return inv


def get_invite_link(db: Session, me: User, group_id: uuid.UUID) -> InviteLink:
    lock_group(db, group_id)
    _live_group_for_member(db, me, group_id)
    inv = _active_invite(db, group_id)
    if inv is None:
        try:
            inv = _new_invite(db, group_id, me.id)
            db.commit()
        except IntegrityError:  # another member created it at the same moment
            db.rollback()
            inv = _active_invite(db, group_id)
    return _link(inv)


def reset_invite_link(db: Session, me: User, group_id: uuid.UUID) -> InviteLink:
    lock_group(db, group_id)
    _live_group_for_member(db, me, group_id)
    old = _active_invite(db, group_id)
    if old is not None:
        old.revoked_at = _now()
        db.flush()
    inv = _new_invite(db, group_id, me.id)
    db.commit()
    return _link(inv)


# ---------- placeholder merge ----------
def _merge_rows(db: Session, model, key_cols: tuple[str, ...], placeholder: uuid.UUID, real: uuid.UUID,
                sum_cols: tuple[str, ...], min_cols: tuple[str, ...] = ()) -> None:
    """Rows of `model` whose `user_id` is the placeholder: move them to `real`; where `real` already has a row with
    the same other key columns, add the amounts into that row and drop the placeholder's."""
    for row in db.scalars(select(model).where(model.user_id == placeholder)).all():
        existing = db.get(model, tuple(real if c == "user_id" else getattr(row, c) for c in key_cols))
        if existing is None:
            db.execute(update(model).where(*(getattr(model, c) == getattr(row, c) for c in key_cols))
                       .values(user_id=real))
            continue
        for col in sum_cols:
            a, b = getattr(existing, col), getattr(row, col)
            setattr(existing, col, None if (a is None or b is None) else a + b)
        for col in min_cols:
            setattr(existing, col, min(getattr(existing, col), getattr(row, col)))
        db.delete(row)
    db.flush()
    db.expire_all()


def merge_placeholder(db: Session, placeholder: User, real: User) -> None:
    """Re-point everything that references `placeholder` to `real`, then retire the placeholder (`merged_into`,
    email/phone cleared, `deleted_at` set so lookups ignore it). Amounts are never recomputed: payer and split rows are
    only re-assigned, and summed when both people were on the same expense, so every expense total still balances."""
    p, r = placeholder.id, real.id
    _merge_rows(db, ExpensePayer, ("expense_id", "user_id"), p, r, ("paid_amount_minor",))
    _merge_rows(db, ExpenseSplit, ("expense_id", "user_id"), p, r, ("owed_amount_minor", "input_value"),
                ("sort_index",))
    for col in ("created_by", "updated_by", "deleted_by"):
        db.execute(update(Expense).where(getattr(Expense, col) == p).values({col: r}))
    now = _now()
    # a payment between the two of them would become a payment to oneself: retire it
    mutual = set(db.scalars(select(Settlement.id).where(
        ((Settlement.from_user_id == p) & (Settlement.to_user_id == r))
        | ((Settlement.from_user_id == r) & (Settlement.to_user_id == p)))))
    if mutual:  # they stay (soft-deleted) pointing at the retired placeholder
        db.execute(update(Settlement).where(Settlement.id.in_(mutual), Settlement.deleted_at.is_(None))
                   .values(deleted_at=now, deleted_by=r))
    for col in ("created_by", "deleted_by"):
        db.execute(update(Settlement).where(getattr(Settlement, col) == p).values({col: r}))
    db.flush()
    for s in db.scalars(select(Settlement).where((Settlement.from_user_id == p) | (Settlement.to_user_id == p))):
        if s.id in mutual:
            continue
        if s.from_user_id == p:
            s.from_user_id = r
        if s.to_user_id == p:
            s.to_user_id = r
    db.execute(update(Comment).where(Comment.user_id == p).values(user_id=r))
    db.execute(update(ActivityLog).where(ActivityLog.actor_id == p).values(actor_id=r))
    db.execute(update(GroupMember).where(GroupMember.added_by == p).values(added_by=r))
    # memberships: the joining user takes over the placeholder's seat (same sort_index keeps remainder order stable)
    for gm in db.scalars(select(GroupMember).where(GroupMember.user_id == p)).all():
        mine = db.get(GroupMember, (gm.group_id, r))
        if mine is None:
            db.execute(update(GroupMember).where(GroupMember.group_id == gm.group_id, GroupMember.user_id == p)
                       .values(user_id=r))
        else:
            if mine.left_at is not None and gm.left_at is None:
                mine.left_at, mine.sort_index, mine.joined_at = None, gm.sort_index, gm.joined_at
            db.delete(gm)
    db.flush()
    db.expire_all()
    # friendships
    for f in db.scalars(select(Friendship).where((Friendship.user_id == p) | (Friendship.friend_id == p))).all():
        other = f.friend_id if f.user_id == p else f.user_id
        status, created, removed = f.status, f.created_at, f.removed_at
        db.delete(f)
        db.flush()
        if other == r:
            continue
        a, b = pair(r, other)
        keep = db.get(Friendship, (a, b))
        if keep is None:
            db.add(Friendship(user_id=a, friend_id=b, status=status, created_at=created, removed_at=removed))
        elif keep.status != "active" and status == "active":
            keep.status, keep.removed_at = "active", None
    placeholder.merged_into = r
    placeholder.email = placeholder.phone_e164 = None
    placeholder.deleted_at = now
    db.flush()


def join_group(db: Session, me: User, req: JoinGroupRequest) -> GroupOut:
    inv = db.scalar(select(GroupInvite).where(GroupInvite.token == req.token.strip(), GroupInvite.revoked_at.is_(None)))
    group = db.get(Group, inv.group_id) if inv is not None else None
    if inv is None or group is None or group.deleted_at is not None:
        raise ApiError(410, "LINK_EXPIRED", "This invite link is no longer valid")
    lock_group(db, group.id)
    if db.scalar(select(GroupInvite.id).where(GroupInvite.id == inv.id, GroupInvite.revoked_at.is_(None))) is None:
        raise ApiError(410, "LINK_EXPIRED", "This invite link is no longer valid")  # reset while we waited
    placeholder = None
    if req.claim_placeholder_user_id is not None:
        placeholder = db.get(User, req.claim_placeholder_user_id)
        seat = db.get(GroupMember, (group.id, req.claim_placeholder_user_id))
        if (placeholder is None or placeholder.is_registered or placeholder.deleted_at is not None or seat is None
                or seat.left_at is not None):
            raise ApiError(422, "VALIDATION_ERROR", "That person is not an unclaimed member of this group",
                           {"fields": [{"field": "claim_placeholder_user_id",
                                        "message": "not an unclaimed placeholder member of this group"}]})
    active = _active_member_ids(db, group.id)
    already = me.id in active
    if not already and placeholder is None and len(active) >= MAX_MEMBERS:
        raise ApiError(422, "GROUP_TOO_LARGE", f"A group can have at most {MAX_MEMBERS} members",
                       {"fields": [{"field": "members", "message": f"at most {MAX_MEMBERS} members"}]})
    if placeholder is not None:
        merge_placeholder(db, placeholder, me)
    mine = db.get(GroupMember, (group.id, me.id))
    if mine is None:
        nxt = (db.scalar(select(GroupMember.sort_index).where(GroupMember.group_id == group.id)
                         .order_by(GroupMember.sort_index.desc()).limit(1)) or 0) + 1
        db.add(GroupMember(group_id=group.id, user_id=me.id, role="member", sort_index=nxt, added_by=inv.created_by))
    elif mine.left_at is not None:
        nxt = (db.scalar(select(GroupMember.sort_index).where(GroupMember.group_id == group.id)
                         .order_by(GroupMember.sort_index.desc()).limit(1)) or 0) + 1
        mine.left_at, mine.sort_index, mine.joined_at, mine.added_by = None, nxt, _now(), inv.created_by
    db.flush()
    if not already:
        group.updated_at = _now()
        activity.record(db, me.id, "group.member_added", "group", group.id, group.id,
                        {"name": group.name, "user_id": str(me.id), "user_name": me.name},
                        _active_member_ids(db, group.id))
    db.commit()
    return group_out(db, group, me)
