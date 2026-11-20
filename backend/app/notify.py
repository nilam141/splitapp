"""Notifications (S6-B-3): who gets a push for an activity event, and delivery of the outbox.

Fan-out writes `notifications` rows in the caller's transaction (`activity.record` calls `fan_out`). Rules:
- never to the actor (no self-notify);
- only to registered users (placeholders have no device) whose `notification_prefs[type]` is true; a disabled type
  writes no row at all;
- the type is one of the 10 F-38 keys (`expense_added`, ...), stored in `notifications.type`.
Delivery (`deliver_pending`, run by the scheduler) sends push rows to the user's devices and email rows by email."""
import logging
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ActivityLog, Notification, PushDevice
from app.senders import EmailSender, PermanentFailure, PushSender, get_email_sender, get_push_sender

log = logging.getLogger("app.notify")
MAX_ATTEMPTS = 3

# Expense, comment and settlement events are pushed. Group and friend events are NOT yet: vectors 52-56 (and
# test_friends.py) assert that those flows write no notification rows at all.
_ACTION_TYPE = {
    "expense.created": "expense_added", "expense.updated": "expense_updated", "expense.deleted": "expense_updated",
    "expense.restored": "expense_updated", "comment.created": "comment_added",
    "settlement.created": "payment_recorded", "settlement.updated": "payment_recorded",
    "settlement.deleted": "payment_recorded", "settlement.restored": "payment_recorded",
}


def notification_type(action: str, payload: Mapping[str, Any], recipient_id: uuid.UUID) -> str | None:
    """The F-38 type of `action`, or None when the action is not pushed."""
    return _ACTION_TYPE.get(action)


def message_for(action: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    who = payload.get("actor_name") or "Someone"
    what = payload.get("description") or payload.get("name") or ""
    if payload.get("recurring"):
        return "SplitApp", f'Recurring expense "{what}" was added'
    verb = {"expense.created": "added", "expense.updated": "edited", "expense.deleted": "deleted",
            "expense.restored": "restored", "comment.created": "commented on"}.get(action)
    if verb:
        return "SplitApp", f'{who} {verb} "{what}"'.strip()
    if action.startswith("settlement."):
        return "SplitApp", f"{who} recorded a payment"
    if action == "friend.added":
        return "SplitApp", f"{who} added you as a friend"
    if action == "friend.removed":
        return "SplitApp", f"{who} removed you as a friend"
    return "SplitApp", f'{who} updated "{what}"'.strip()


def fan_out(db: Session, log_row: ActivityLog, prefs_by_user: Mapping[uuid.UUID, Mapping[str, Any]]) -> int:
    """Queue one push row per eligible recipient of `log_row`. Returns the number of rows queued."""
    n = 0
    title, body = message_for(log_row.action, log_row.payload)
    for uid in sorted(prefs_by_user, key=str):
        if uid == log_row.actor_id:
            continue
        type_ = notification_type(log_row.action, log_row.payload, uid)
        if type_ is None or not (prefs_by_user[uid] or {}).get(type_, True):
            continue
        db.add(Notification(user_id=uid, type=type_, channel="push", activity_id=log_row.id, status="pending",
                            attempts=0, payload={"title": title, "body": body, "action": log_row.action,
                                                 "entity_type": log_row.entity_type,
                                                 "entity_id": str(log_row.entity_id),
                                                 "group_id": str(log_row.group_id) if log_row.group_id else None}))
        n += 1
    return n


# ---------- email rendering ----------
def render_email(type_: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    if type_ == "password_reset":
        return ("Reset your SplitApp password",
                f"Use this link to choose a new password (valid for 60 minutes):\n"
                f"{settings.reset_url_base}{payload['token']}\n\nIf you did not ask for this, ignore this email.")
    if type_ == "invite":
        where = f' to the group "{payload["group"]}"' if payload.get("group") else ""
        return (f"{payload.get('inviter_name', 'A friend')} invited you to SplitApp",
                f"{payload.get('inviter_name', 'A friend')} invited you{where}. "
                "Install SplitApp and sign up with this email address to see what you share.")
    if type_ == "reminder":
        note = f"\n\n\"{payload['message']}\"" if payload.get("message") else ""
        return (f"{payload.get('from_name', 'A friend')} sent you a reminder",
                f"{payload.get('from_name', 'A friend')} reminded you to settle up.{note}")
    return ("SplitApp", str(payload.get("body", "")))


# ---------- delivery ----------
def _deliver_one(db: Session, n: Notification, push: PushSender, email: EmailSender) -> None:
    if n.channel == "email":
        subject, body = render_email(n.type, n.payload)
        email.send(n.payload["to"], subject, body)
        return
    tokens = list(db.scalars(select(PushDevice.token).where(PushDevice.user_id == n.user_id)))
    if not tokens:
        raise PermanentFailure("no registered device")
    data = {k: str(v) for k, v in n.payload.items() if k not in ("title", "body") and v is not None}
    sent = 0
    for token in tokens:
        try:
            push.send(token, n.payload.get("title", "SplitApp"), n.payload.get("body", ""), data)
            sent += 1
        except PermanentFailure:
            db.query(PushDevice).filter(PushDevice.token == token).delete()  # dead token: forget it
    if not sent:
        raise PermanentFailure("no live device")


def deliver_pending(db: Session, push: PushSender | None = None, email: EmailSender | None = None,
                    limit: int = 100) -> dict[str, int]:
    """Send pending outbox rows once. Success -> `sent`; a permanent failure -> `failed`; any other error counts an
    attempt and the row stays `pending` until MAX_ATTEMPTS, then `failed`."""
    push = push or get_push_sender()
    email = email or get_email_sender()
    rows = db.scalars(select(Notification).where(Notification.status == "pending")
                      .order_by(Notification.created_at, Notification.id).limit(limit)
                      .with_for_update(skip_locked=True)).all()
    result = {"sent": 0, "failed": 0, "retry": 0}
    for n in rows:
        n.attempts += 1
        try:
            _deliver_one(db, n, push, email)
            n.status, n.sent_at = "sent", datetime.now(timezone.utc)
            result["sent"] += 1
        except PermanentFailure as exc:
            log.info("notification %s not delivered: %s", n.id, exc)
            n.status = "failed"
            result["failed"] += 1
        except Exception:  # noqa: BLE001 - one bad row must not stop the batch
            log.exception("notification %s failed (attempt %s)", n.id, n.attempts)
            if n.attempts >= MAX_ATTEMPTS:
                n.status = "failed"
                result["failed"] += 1
            else:
                result["retry"] += 1
        n.updated_at = datetime.now(timezone.utc)
    db.commit()
    return result
