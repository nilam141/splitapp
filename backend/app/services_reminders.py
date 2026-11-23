"""Settle-up reminders (S6-B-3, business_rules 10.3, OQ-34). There is deliberately NO check that the recipient owes the
sender. Checks: the recipient exists and is not the sender; they are a friend (derived list) or both are current members
of `group_id` when it is given (else 422 VALIDATION_ERROR); then the rate limit of 1 per (sender, recipient) per 60 s.
The reminder is one outbox row, an email when the recipient has an address (the contract says "email a reminder") and a
push otherwise, and none if the recipient switched the `reminder` notification off. The reminder itself is still
recorded and counted against the rate limit."""
import uuid

from sqlalchemy.orm import Session

from app import rate_limit
from app.errors import ApiError
from app.models import Group, GroupMember, Notification, Reminder, User
from app.schemas import ReminderCreate
from app.services_friends import _visible_friend

WINDOW_SECONDS = 60


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": field, "message": message}]})


def _co_members(db: Session, group_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID) -> bool:
    for uid in (a, b):
        row = db.get(GroupMember, (group_id, uid))
        if row is None or row.left_at is not None:
            return False
    return True


def create_reminder(db: Session, me: User, req: ReminderCreate) -> None:
    if req.to_user_id == me.id:
        raise _invalid("to_user_id", "You cannot remind yourself")
    target = db.get(User, req.to_user_id)
    if target is None or target.deleted_at is not None:
        raise _invalid("to_user_id", "Unknown recipient")
    group = db.get(Group, req.group_id) if req.group_id is not None else None
    allowed = (group is not None and group.deleted_at is None and _co_members(db, group.id, me.id, target.id)) \
        or _visible_friend(db, me, target.id) is not None
    if not allowed:
        raise _invalid("to_user_id", "The recipient must be a friend or a member of the group")
    key = f"{me.id}:{target.id}"
    rate_limit.check(db, [("reminder", key, 1, WINDOW_SECONDS)])
    rate_limit.record(db, "reminder", key, WINDOW_SECONDS)
    db.add(Reminder(id=uuid.uuid4(), from_user_id=me.id, to_user_id=target.id, group_id=req.group_id,
                    message=req.message))
    if (target.notification_prefs or {}).get("reminder", True):
        text = req.message or "Please settle up when you can."
        if target.email:
            payload = {"to": target.email, "from_name": me.name, "message": req.message,
                       "group": group.name if group else None}
            channel = "email"
        else:
            payload = {"title": me.name, "body": text, "action": "reminder", "entity_type": "reminder",
                       "entity_id": str(me.id), "group_id": str(req.group_id) if req.group_id else None}
            channel = "push"
        db.add(Notification(user_id=target.id, type="reminder", channel=channel, payload=payload, status="pending",
                            attempts=0))
    db.commit()
