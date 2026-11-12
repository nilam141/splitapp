"""Balances read from the database (S4-B-2). Rows are loaded in a fixed number of queries and handed to the pure
functions in app.balances; there is no per-expense or per-member query. Only live (non-deleted) expenses count.
Settlements join in with Slice 5 (the table does not exist yet); the pure functions already accept them."""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import balances as pure
from app.errors import ApiError
from app.models import Expense, ExpensePayer, ExpenseSplit, Group, GroupMember
from app.schemas import BalanceLine, GroupBalances, GroupBalanceMember, OverallBalances, OverallFriend, Transfer


def lines(by_currency: dict[str, int]) -> list[BalanceLine]:
    """Non-zero lines, ordered by currency code."""
    return [BalanceLine(amount_minor=v, currency=c) for c, v in sorted(by_currency.items()) if v != 0]


def _aware(ts: datetime) -> datetime:
    """SQLite returns naive timestamps; every stored timestamp is UTC."""
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _load_expenses(db: Session, cond) -> list[dict[str, Any]]:
    """Live expenses matching `cond` as plain records (plus id, group_id, created_at): three queries."""
    base = [Expense.deleted_at.is_(None), cond]
    recs: dict[uuid.UUID, dict[str, Any]] = {}
    for eid, gid, cur, created in db.execute(
            select(Expense.id, Expense.group_id, Expense.currency, Expense.created_at).where(*base)):
        recs[eid] = {"id": eid, "group_id": gid, "currency": cur, "created_at": _aware(created), "payers": [], "splits": []}
    if not recs:
        return []
    for eid, uid, paid in db.execute(
            select(ExpensePayer.expense_id, ExpensePayer.user_id, ExpensePayer.paid_amount_minor)
            .join(Expense, Expense.id == ExpensePayer.expense_id).where(*base)):
        recs[eid]["payers"].append((uid, paid))
    for eid, uid, owed in db.execute(
            select(ExpenseSplit.expense_id, ExpenseSplit.user_id, ExpenseSplit.owed_amount_minor)
            .join(Expense, Expense.id == ExpenseSplit.expense_id).where(*base).order_by(ExpenseSplit.sort_index)):
        recs[eid]["splits"].append((uid, owed))
    return list(recs.values())


@dataclass
class GroupData:
    id: uuid.UUID
    name: str
    simplify_debts: bool
    created_at: datetime
    canonical: list[uuid.UUID]          # every member ever, by sort_index (departed members keep their place)
    active: list[uuid.UUID]             # current members, canonical order
    expenses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def nets(self) -> dict[str, dict[uuid.UUID, int]]:
        return pure.net_balances(self.expenses)

    def settled_up_since(self) -> datetime | None:
        """Latest live event once every net in the group is 0; null while any net is non-zero or with no activity."""
        if not self.expenses or any(v for nets in self.nets.values() for v in nets.values()):
            return None
        return max(e["created_at"] for e in self.expenses)


def load_groups(db: Session, group_ids: list[uuid.UUID]) -> dict[uuid.UUID, GroupData]:
    if not group_ids:
        return {}
    data: dict[uuid.UUID, GroupData] = {}
    for g in db.scalars(select(Group).where(Group.id.in_(group_ids))):
        data[g.id] = GroupData(g.id, g.name, g.simplify_debts, g.created_at, [], [])
    for gid, uid, left in db.execute(
            select(GroupMember.group_id, GroupMember.user_id, GroupMember.left_at)
            .where(GroupMember.group_id.in_(group_ids)).order_by(GroupMember.sort_index, GroupMember.user_id)):
        data[gid].canonical.append(uid)
        if left is None:
            data[gid].active.append(uid)
    for rec in _load_expenses(db, Expense.group_id.in_(group_ids)):
        data[rec["group_id"]].expenses.append(rec)
    return data


# ---------- group endpoints ----------
def _require_member(db: Session, me_id: uuid.UUID, group_id: uuid.UUID) -> None:
    if db.get(Group, group_id) is None:
        raise ApiError(404, "NOT_FOUND", "Group not found")
    m = db.get(GroupMember, (group_id, me_id))
    if m is None or m.left_at is not None:
        raise ApiError(403, "FORBIDDEN", "You are not a member of this group")


def group_balances(db: Session, me_id: uuid.UUID, group_id: uuid.UUID) -> GroupBalances:
    _require_member(db, me_id, group_id)
    g = load_groups(db, [group_id])[group_id]
    nets = g.nets
    members = [GroupBalanceMember(user_id=u, balances=lines({c: n.get(u, 0) for c, n in nets.items()}))
               for u in g.active]
    by_currency = pure.suggested_transfers(g.expenses, (), g.canonical, g.simplify_debts)
    transfers = [Transfer(from_user_id=f, to_user_id=t, amount_minor=a, currency=c)
                 for c in sorted(by_currency) for f, t, a in by_currency[c]]
    return GroupBalances(group_id=group_id, simplified=g.simplify_debts, members=members, transfers=transfers)


def member_lines(group: GroupData, user_id: uuid.UUID) -> list[BalanceLine]:
    return lines({c: n.get(user_id, 0) for c, n in group.nets.items()})


def user_group_balances(db: Session, user_id: uuid.UUID, group_id: uuid.UUID) -> list[BalanceLine]:
    """One member's non-zero nets in one group (the leave/remove guard)."""
    return member_lines(load_groups(db, [group_id])[group_id], user_id)


# ---------- pairs: me versus each other user ----------
@dataclass
class Pairs:
    total: dict[uuid.UUID, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    non_group: dict[uuid.UUID, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    groups: list[tuple[GroupData, dict[uuid.UUID, dict[str, int]]]] = field(default_factory=list)
    last_event: dict[uuid.UUID, datetime] = field(default_factory=dict)


def _my_edges(me_id: uuid.UUID, by_currency: dict[str, list[pure.Transfer]]) -> dict[uuid.UUID, dict[str, int]]:
    """Edges that touch me, as the other person's balance (positive = they owe me)."""
    out: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cur, rows in by_currency.items():
        for frm, to, amount in rows:
            if to == me_id:
                out[frm][cur] += amount
            elif frm == me_id:
                out[to][cur] -= amount
    return out


def compute_pairs(db: Session, me_id: uuid.UUID, with_groups: bool = True) -> Pairs:
    """business_rules 4.3: per other user, the sum over my live groups of the suggested edge (simplified or pairwise
    by the group's toggle) plus the pairwise non-group balance."""
    pairs = Pairs()
    group_ids = list(db.scalars(
        select(Group.id).join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == me_id, GroupMember.left_at.is_(None), Group.deleted_at.is_(None)))
    ) if with_groups else []
    groups = sorted(load_groups(db, group_ids).values(), key=lambda g: (g.created_at, g.id))
    involving_me = (Expense.id.in_(select(ExpensePayer.expense_id).where(ExpensePayer.user_id == me_id))
                    | Expense.id.in_(select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == me_id)))
    non_group = _load_expenses(db, Expense.group_id.is_(None) & involving_me)

    def note(expense: dict[str, Any], at: datetime | None = None) -> None:
        parties = {u for u, _ in expense["payers"]} | {u for u, _ in expense["splits"]}
        if me_id in parties:
            when = max(expense["created_at"], at) if at is not None else expense["created_at"]
            for p in parties - {me_id}:
                if p not in pairs.last_event or when > pairs.last_event[p]:
                    pairs.last_event[p] = when

    for g in groups:
        mine = _my_edges(me_id, pure.suggested_transfers(g.expenses, (), g.canonical, g.simplify_debts))
        pairs.groups.append((g, mine))
        for f, cur_map in mine.items():
            for cur, v in cur_map.items():
                pairs.total[f][cur] += v
        for e in g.expenses:
            note(e)
    users = sorted({u for e in non_group for u, _ in (*e["payers"], *e["splits"])}, key=lambda u: u.int)
    for f, cur_map in _my_edges(me_id, pure.pairwise_edges(non_group, (), users)).items():
        for cur, v in cur_map.items():
            pairs.non_group[f][cur] += v
            pairs.total[f][cur] += v
    for e in non_group:
        note(e)
    if with_groups:
        # Groups I have left (live groups only) still date the settled-up state: the later of the expense and my
        # leave time. Only groups I was a member of are read; they never add to balances (the leave guard keeps
        # my net there at 0).
        left_at = {gid: _aware(left) for gid, left in db.execute(
            select(GroupMember.group_id, GroupMember.left_at)
            .join(Group, Group.id == GroupMember.group_id)
            .where(GroupMember.user_id == me_id, GroupMember.left_at.is_not(None), Group.deleted_at.is_(None)))}
        if left_at:
            for e in _load_expenses(db, Expense.group_id.in_(list(left_at)) & involving_me):
                note(e, left_at[e["group_id"]])
    return pairs


def friend_fields(pairs: Pairs, friend_id: uuid.UUID) -> tuple[list[BalanceLine], list[dict[str, Any]], datetime | None]:
    """(balances, breakdown, settled_up_since) for one friend."""
    total = lines(pairs.total.get(friend_id, {}))
    breakdown: list[dict[str, Any]] = []
    ng = lines(pairs.non_group.get(friend_id, {}))
    if ng:
        breakdown.append({"scope": "non_group", "group_id": None, "group_name": None, "balances": ng})
    for g, mine in pairs.groups:
        part = lines(mine.get(friend_id, {}))
        if part:
            breakdown.append({"scope": "group", "group_id": g.id, "group_name": g.name, "balances": part})
    since = None if total else pairs.last_event.get(friend_id)
    return total, breakdown, since


def non_group_total(pairs: Pairs) -> list[BalanceLine]:
    """The viewer's signed total over all non-group expenses, per currency."""
    out: dict[str, int] = defaultdict(int)
    for cur_map in pairs.non_group.values():
        for cur, v in cur_map.items():
            out[cur] += v
    return lines(out)


def overall_balances(db: Session, me_id: uuid.UUID) -> OverallBalances:
    pairs = compute_pairs(db, me_id)
    owed: dict[str, int] = defaultdict(int)
    owe: dict[str, int] = defaultdict(int)
    by_friend = []
    for f in sorted(pairs.total, key=lambda u: u.int):
        ls = lines(pairs.total[f])
        if not ls:
            continue
        by_friend.append(OverallFriend(user_id=f, balances=ls))
        for b in ls:
            if b.amount_minor > 0:
                owed[b.currency] += b.amount_minor
            else:
                owe[b.currency] += -b.amount_minor
    return OverallBalances(you_are_owed=lines(owed), you_owe=lines(owe), by_friend=by_friend)
