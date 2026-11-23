"""Recurring expenses (S6-B-1, S6-B-2). Date and split arithmetic is in `app.recurrence` (pure); this module is the
database side: rule CRUD and the job that creates due occurrences and queues reminders.

Authorization: a group rule is visible to and changeable by the group's current members; a non-group rule by the users
on its template expense. Occurrences are created by the system (activity `actor_id` null) with `created_by` = the
rule's creator. When a participant has left the group (or, for a non-group rule, is no longer a friend of the creator)
the occurrence drops them (business_rules 8, vectors 36-38); if nobody can be left to pay or share, or the template or
the group is deleted, the rule is deactivated."""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import activity, recurrence
from app.errors import ApiError
from app.models import Expense, ExpensePayer, ExpenseSplit, Group, GroupMember, Notification, RecurringRule, User
from app.schemas_expenses import MoneyOut
from app.schemas_recurring import RecurringCreate, RecurringList, RecurringRuleOut, RecurringUpdate
from app.splits import SplitError

log = logging.getLogger("app.recurring")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today(rule: RecurringRule, now: datetime) -> date:
    try:
        return now.astimezone(ZoneInfo(rule.time_zone)).date()
    except Exception:  # noqa: BLE001 - an unknown zone must not stop the job; UTC is the safe fallback
        return now.date()


# ---------- output ----------
def rule_out(rule: RecurringRule, template: Expense) -> RecurringRuleOut:
    return RecurringRuleOut(
        id=rule.id, template_expense_id=rule.template_expense_id, group_id=template.group_id,
        description=template.description,
        total=MoneyOut(amount_minor=template.total_amount_minor, currency=template.currency),
        interval=rule.interval, anchor_date=rule.anchor_date, next_occurrence_date=rule.next_occurrence_date,
        reminder_days_before=rule.reminder_days_before, active=rule.active)


# ---------- creating ----------
def attach_rule(db: Session, me: User, template: Expense, interval: str, reminder_days: int | None) -> RecurringRule:
    """Make `template` the first occurrence of a new rule. The expense row exists first; the rule is inserted, then the
    expense gets the rule id and `occurrence_date = anchor_date` (data_model `expenses.recurring_rule_id`)."""
    anchor = template.expense_date
    rule = RecurringRule(id=uuid.uuid4(), template_expense_id=template.id, interval=interval, anchor_date=anchor,
                         next_occurrence_date=recurrence.occurrence(anchor, interval, 1),
                         reminder_days_before=reminder_days, time_zone=me.time_zone, active=True, created_by=me.id)
    db.add(rule)
    db.flush()
    template.recurring_rule_id = rule.id
    template.occurrence_date = anchor
    db.flush()
    return rule


# ---------- access ----------
def _can_see(db: Session, me: User, template: Expense) -> bool:
    if template.group_id is not None:
        row = db.get(GroupMember, (template.group_id, me.id))
        return row is not None and row.left_at is None
    return me.id in _involved(db, template.id)


def _involved(db: Session, expense_id: uuid.UUID) -> set[uuid.UUID]:
    return (set(db.scalars(select(ExpensePayer.user_id).where(ExpensePayer.expense_id == expense_id)))
            | set(db.scalars(select(ExpenseSplit.user_id).where(ExpenseSplit.expense_id == expense_id))))


def _load(db: Session, me: User, rule_id: uuid.UUID) -> tuple[RecurringRule, Expense]:
    rule = db.get(RecurringRule, rule_id)
    if rule is None:
        raise ApiError(404, "NOT_FOUND", "Recurring rule not found")
    template = db.get(Expense, rule.template_expense_id)
    if template is None or not _can_see(db, me, template):
        raise ApiError(403, "FORBIDDEN", "You cannot access this recurring rule")
    return rule, template


def _invalid(field: str, message: str, status: int = 422) -> ApiError:
    return ApiError(status, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


# ---------- endpoints ----------
def list_rules(db: Session, me: User, group_id: uuid.UUID | None) -> RecurringList:
    my_groups = (select(GroupMember.group_id).join(Group, Group.id == GroupMember.group_id)
                 .where(GroupMember.user_id == me.id, GroupMember.left_at.is_(None), Group.deleted_at.is_(None)))
    from app.services_expenses import _involving  # local import: services_expenses imports this module
    stmt = (select(RecurringRule, Expense).join(Expense, Expense.id == RecurringRule.template_expense_id)
            .where(or_(Expense.group_id.in_(my_groups),
                       and_(Expense.group_id.is_(None), Expense.id.in_(_involving(me.id)))))
            .order_by(RecurringRule.next_occurrence_date, RecurringRule.id))
    if group_id is not None:
        stmt = stmt.where(Expense.group_id == group_id)
    return RecurringList(items=[rule_out(r, e) for r, e in db.execute(stmt).all()])


def create_rule(db: Session, me: User, req: RecurringCreate) -> RecurringRuleOut:
    from app.services_expenses import _load_visible
    from app.services_groups import lock_group
    template = _load_visible(db, me, req.template_expense_id)
    if template.group_id is not None:
        lock_group(db, template.group_id)
        db.refresh(template)
    if template.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The expense has been deleted")
    if template.group_id is not None and db.get(Group, template.group_id).deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "The group has been deleted")
    if template.recurring_rule_id is not None:
        raise _invalid("template_expense_id", "This expense already repeats", 409)
    try:
        rule = attach_rule(db, me, template, req.interval, req.reminder_days_before)
        db.commit()
    except IntegrityError:  # two requests raced on the same expense
        db.rollback()
        raise _invalid("template_expense_id", "This expense already repeats", 409)
    return rule_out(rule, template)


def update_rule(db: Session, me: User, rule_id: uuid.UUID, req: RecurringUpdate) -> RecurringRuleOut:
    rule, template = _load(db, me, rule_id)
    sent = req.model_fields_set
    if "interval" in sent and req.interval is None:
        raise _invalid("interval", "interval cannot be null")
    if "active" in sent and req.active is None:
        raise _invalid("active", "active cannot be null")
    today = _today(rule, _now())
    last = db.scalar(select(Expense.occurrence_date).where(Expense.recurring_rule_id == rule.id)
                     .order_by(Expense.occurrence_date.desc()).limit(1)) or rule.anchor_date
    regrid = False
    if "interval" in sent and req.interval != rule.interval:
        rule.interval, regrid = req.interval, True
    if "reminder_days_before" in sent:
        rule.reminder_days_before = req.reminder_days_before
    if "active" in sent and req.active != rule.active:
        rule.active = req.active
        regrid = regrid or req.active  # resuming: continue from today, do not back-fill the pause
    if regrid:
        # the next occurrence on the (possibly new) grid after the last one created, and never in the past on resume
        floor = max(last, today - timedelta(days=1)) if "active" in sent and rule.active else last
        rule.next_occurrence_date = recurrence.next_after(rule.anchor_date, rule.interval, floor)
        rule.last_reminded_for = None
    rule.updated_at = _now()
    db.commit()
    return rule_out(rule, template)


def delete_rule(db: Session, me: User, rule_id: uuid.UUID) -> None:
    """Past occurrences are kept; they lose the link to the rule (the foreign key would otherwise block the delete)."""
    rule, _ = _load(db, me, rule_id)
    for e in db.scalars(select(Expense).where(Expense.recurring_rule_id == rule.id)):
        e.recurring_rule_id = None
        e.occurrence_date = None
    db.flush()
    db.delete(rule)
    db.commit()


# ---------- the job (S6-B-2) ----------
def _remaining(db: Session, rule: RecurringRule, template: Expense, involved: set[uuid.UUID]) -> set[uuid.UUID] | None:
    """Who can still take part, or None when the rule cannot continue (group deleted)."""
    if template.group_id is not None:
        group = db.get(Group, template.group_id)
        if group is None or group.deleted_at is not None:
            return None
        return set(db.scalars(select(GroupMember.user_id).where(
            GroupMember.group_id == template.group_id, GroupMember.left_at.is_(None),
            GroupMember.user_id.in_(involved))))
    from app.services_friends import _visible_friend
    creator = db.get(User, rule.created_by)
    return {u for u in involved if u == rule.created_by or (creator is not None and _visible_friend(db, creator, u))}


def _deactivate(rule: RecurringRule, why: str) -> None:
    log.info("recurring rule %s deactivated: %s", rule.id, why)
    rule.active = False
    rule.updated_at = _now()


def _make_occurrence(db: Session, rule: RecurringRule, template: Expense, day: date) -> Expense | None:
    """Create the occurrence dated `day`. Returns None when it already exists or the rule had to be deactivated."""
    from app.services_expenses import _nets, _payers_of, _splits_of, _write_rows
    if db.scalar(select(Expense.id).where(Expense.recurring_rule_id == rule.id, Expense.occurrence_date == day)):
        return None  # already created (an earlier or concurrent run): the job is idempotent
    payers = _payers_of(db, template.id)
    stored = _splits_of(db, template.id)
    involved = {u for u, _ in payers} | {r[0] for r in stored}
    remaining = _remaining(db, rule, template, involved)
    if remaining is None:
        _deactivate(rule, "group deleted")
        return None
    new_payers = recurrence.rebase_payers(template.total_amount_minor, payers, remaining)
    try:
        if new_payers is None:
            raise ValueError("no payer remains")
        split_type, entries, owed = recurrence.occurrence_amounts(
            template.split_type, template.total_amount_minor, [(u, v, o) for u, o, v, _ in stored], remaining)
    except (ValueError, SplitError) as exc:
        _deactivate(rule, str(exc))
        return None
    rows = [(u, owed[u], None if split_type == "equal" else v, i) for i, (u, v) in enumerate(entries)]
    now = _now()
    e = Expense(id=uuid.uuid4(), group_id=template.group_id, description=template.description,
                total_amount_minor=template.total_amount_minor, currency=template.currency,
                category_id=template.category_id, notes=template.notes, expense_date=day, split_type=split_type,
                created_by=rule.created_by, recurring_rule_id=rule.id, occurrence_date=day, version=1,
                created_at=now, updated_at=now)
    db.add(e)
    db.flush()
    _write_rows(db, e.id, new_payers, rows)
    nets = _nets(new_payers, rows)
    users = set(nets)
    payload = {"description": e.description, "recurring": True,
               "total": {"amount_minor": e.total_amount_minor, "currency": e.currency}, "actor_name": None}
    activity.record(db, None, "expense.created", "expense", e.id, e.group_id, payload, users,
                    {u: {e.currency: n} for u, n in nets.items()})
    return e


def _queue_reminder(db: Session, rule: RecurringRule, template: Expense) -> None:
    owner = db.get(User, rule.created_by)
    rule.last_reminded_for = rule.next_occurrence_date
    if owner is None or not owner.is_registered or not (owner.notification_prefs or {}).get("reminder", True):
        return
    db.add(Notification(
        user_id=owner.id, type="reminder", channel="push", status="pending", attempts=0,
        payload={"title": "SplitApp", "body": f'"{template.description}" repeats on {rule.next_occurrence_date}',
                 "action": "recurring.upcoming", "entity_type": "recurring_rule", "entity_id": str(rule.id),
                 "group_id": str(template.group_id) if template.group_id else None,
                 "occurrence_date": rule.next_occurrence_date.isoformat()}))


def run_rule(db: Session, rule_id: uuid.UUID, now: datetime) -> int:
    """One rule: queue its reminder if due, then create every occurrence up to today (catch-up after an outage).
    Returns the number of expenses created. Commits (or rolls back) its own work."""
    rule = db.scalar(select(RecurringRule).where(RecurringRule.id == rule_id).with_for_update())
    if rule is None or not rule.active:
        db.rollback()
        return 0
    created = 0
    try:
        template = db.get(Expense, rule.template_expense_id)
        today = _today(rule, now)
        if template is None or template.deleted_at is not None:
            _deactivate(rule, "template expense deleted")
        else:
            until = (rule.next_occurrence_date - today).days
            if (rule.reminder_days_before is not None and rule.last_reminded_for != rule.next_occurrence_date
                    and 0 <= until <= rule.reminder_days_before):
                _queue_reminder(db, rule, template)
            days = recurrence.due_dates(rule.anchor_date, rule.interval, rule.next_occurrence_date, today)
            for day in days:
                if not rule.active:
                    break
                if _make_occurrence(db, rule, template, day) is not None:
                    created += 1
                if rule.active:
                    rule.next_occurrence_date = recurrence.next_after(rule.anchor_date, rule.interval, day)
        rule.updated_at = now
        db.commit()
    except IntegrityError:  # a concurrent run created the same occurrence; its work stands
        db.rollback()
        return 0
    return created


def run_due(db: Session, now: datetime | None = None) -> int:
    """Create every due occurrence of every active rule. Safe to run any number of times, concurrently or not:
    `(recurring_rule_id, occurrence_date)` is unique and each rule is processed under a row lock."""
    now = now or _now()
    ids = list(db.scalars(select(RecurringRule.id).where(
        RecurringRule.active.is_(True),
        # a rule is looked at from 7 days (the longest reminder lead) + 1 day (time-zone offset) before its date
        RecurringRule.next_occurrence_date <= now.date() + timedelta(days=8))))
    total = 0
    for rid in ids:
        total += run_rule(db, rid, now)
    return total
