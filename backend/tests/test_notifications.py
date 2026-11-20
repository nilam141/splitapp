"""S6-B-3: push fan-out (no self-notify, per-type prefs), POST /reminders (vector 45, OQ-34), delivery and senders."""
import json
import smtplib
import uuid

import httpx
import pytest
from sqlalchemy import select

from app import notify, senders
from app.models import Notification, PushDevice, Reminder
from tests import clock as clockmod
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user


@pytest.fixture()
def clock(monkeypatch):
    return clockmod.install(monkeypatch)


def rows(db, **where):
    db.expire_all()
    stmt = select(Notification)
    for k, v in where.items():
        stmt = stmt.where(getattr(Notification, k) == v)
    return db.scalars(stmt.order_by(Notification.created_at)).all()


def pushes(db, user_dict, type_=None):
    kw = {"user_id": uuid.UUID(uid(user_dict)), "channel": "push"}
    if type_:
        kw["type"] = type_
    return rows(db, **kw)


@pytest.fixture()
def abc(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    return a, b, c, make_group(client, a, [b, c])


# ---------- fan-out ----------
def test_b_adds_an_expense_one_push_for_a_and_c_none_for_b(client, db_session, abc):
    a, b, c, gid = abc
    create_group_expense(client, b, gid, equal_body(b, [a, b, c]))
    assert [r.type for r in pushes(db_session, a)] == ["expense_added"]
    assert [r.type for r in pushes(db_session, c)] == ["expense_added"]
    assert pushes(db_session, b) == []
    row = pushes(db_session, a)[0]
    assert row.status == "pending" and row.activity_id is not None
    assert row.payload["action"] == "expense.created" and row.payload["body"] == 'Ravi added "Dinner"'
    assert row.payload["group_id"] == gid


def test_disabling_a_type_writes_no_row_for_that_user_only(client, db_session, abc):
    a, b, c, gid = abc
    client.patch("/users/me", json={"notification_prefs": {"comment_added": False}}, headers=h(a))
    e = create_group_expense(client, b, gid, equal_body(b, [a, b, c]))
    assert client.post(f"/expenses/{e['id']}/comments", json={"body": "hi"}, headers=h(b)).status_code == 201
    assert pushes(db_session, a, "comment_added") == []
    assert len(pushes(db_session, c, "comment_added")) == 1
    assert pushes(db_session, b, "comment_added") == []
    assert len(pushes(db_session, a, "expense_added")) == 1  # other types are unaffected


def test_expense_events_use_their_own_types(client, db_session, abc):
    a, b, c, gid = abc
    e = create_group_expense(client, a, gid, equal_body(a, [a, b, c]))
    client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 12000, "currency": "INR"}}, headers=h(a))
    client.delete(f"/expenses/{e['id']}", headers=h(a))
    client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert [r.type for r in pushes(db_session, b)] == ["expense_added", "expense_updated", "expense_updated", "expense_updated"]
    assert pushes(db_session, a) == []


def test_settlement_pushes_payment_recorded_to_the_other_party(client, db_session, abc):
    a, b, c, gid = abc
    create_group_expense(client, a, gid, equal_body(a, [a, b, c]))
    pay = {"group_id": gid, "from_user_id": uid(b), "to_user_id": uid(a),
           "amount": {"amount_minor": 1000, "currency": "INR"}, "settled_on": "2026-11-05"}
    assert client.post("/settlements", json=pay, headers=h(b)).status_code == 201
    assert [r.type for r in pushes(db_session, a)] == ["payment_recorded"]
    assert pushes(db_session, b, "payment_recorded") == []


def test_placeholders_get_no_push(client, db_session):
    a = user(client, "Asha")
    g = client.post("/groups", json={"name": "G", "new_members": [{"name": "Kiran", "email": "kiran@example.com"}]},
                    headers=h(a)).json()
    kiran = next(m["user"]["id"] for m in g["members"] if m["user"]["name"] == "Kiran")
    create_group_expense(client, a, g["id"], {**equal_body(a, [a]), "split": {"type": "equal", "entries": [{"user_id": uid(a)}, {"user_id": kiran}]}})
    assert rows(db_session, user_id=uuid.UUID(kiran), channel="push") == []


# ---------- POST /reminders (S6-Q-4, vector 45) ----------
@pytest.fixture()
def ab(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    return a, b, gid


def remind(client, frm, to, **extra):
    return client.post("/reminders", json={"to_user_id": uid(to), **extra}, headers=h(frm))


def test_vector_45_reminder_without_debt_is_accepted_then_rate_limited(client, db_session, ab, clock):
    a, b, _ = ab
    clock.set(0)
    r = remind(client, a, b)  # nobody owes anybody anything
    assert r.status_code == 202 and r.content == b""
    got = rows(db_session, user_id=uuid.UUID(uid(b)), type="reminder")
    assert len(got) == 1 and got[0].channel == "email" and got[0].payload["to"] == "ravi@example.com"
    assert got[0].payload["from_name"] == "Asha" and got[0].status == "pending"
    assert db_session.scalars(select(Reminder)).all()[0].to_user_id == uuid.UUID(uid(b))
    clock.set(30)
    r2 = remind(client, a, b)
    assert r2.status_code == 429 and r2.json()["code"] == "RATE_LIMITED"
    assert 1 <= r2.json()["details"]["retry_after_seconds"] <= 60
    assert len(rows(db_session, type="reminder")) == 1  # the limited call queued nothing
    clock.set(61)
    assert remind(client, a, b).status_code == 202


def test_rate_limit_is_per_sender_and_recipient_pair(client, ab, clock):
    a, b, gid = ab
    c = user(client, "Meera")
    client.post(f"/groups/{gid}/members", json={"user_ids": [uid(c)]}, headers=h(a))
    clock.set(0)
    assert remind(client, a, b).status_code == 202
    assert remind(client, a, c).status_code == 202   # another recipient
    assert remind(client, b, a).status_code == 202   # the other direction
    assert remind(client, a, b).status_code == 429


def test_reminder_to_a_stranger_or_self_or_unknown_is_422(client, ab):
    a, b, _ = ab
    d = user(client, "Dev")
    for r in (remind(client, a, d), remind(client, a, a), client.post("/reminders", json={"to_user_id": str(uuid.uuid4())}, headers=h(a))):
        assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    other = make_group(client, d, [])
    assert remind(client, a, d, group_id=other).status_code == 422  # a group neither of them is in


def test_reminder_to_a_group_co_member_who_is_not_a_friend(client, db_session, ab):
    a, b, gid = ab
    assert remind(client, a, b, group_id=gid, message="rent please").status_code == 202
    assert rows(db_session, type="reminder")[0].payload["message"] == "rent please"


def test_reminder_validation_and_auth(client, ab):
    a, b, _ = ab
    assert remind(client, a, b, message="x" * 1001).status_code == 422
    assert client.post("/reminders", json={}, headers=h(a)).status_code == 422
    assert client.post("/reminders", json={"to_user_id": uid(b)}).status_code == 401


def test_reminder_preference_off_still_202_but_queues_nothing(client, db_session, ab, clock):
    a, b, _ = ab
    client.patch("/users/me", json={"notification_prefs": {"reminder": False}}, headers=h(b))
    clock.set(0)
    assert remind(client, a, b).status_code == 202
    assert rows(db_session, type="reminder") == []
    clock.set(5)
    assert remind(client, a, b).status_code == 429  # it was still recorded and counted


def test_reminder_to_someone_without_an_email_is_a_push(client, db_session):
    a = user(client, "Asha")
    g = client.post("/groups", json={"name": "G", "new_members": [{"name": "Lee", "phone_e164": "+919800000001"}]}, headers=h(a)).json()
    lee = next(m["user"]["id"] for m in g["members"] if m["user"]["name"] == "Lee")
    assert client.post("/reminders", json={"to_user_id": lee, "group_id": g["id"]}, headers=h(a)).status_code == 202
    [row] = rows(db_session, type="reminder")
    assert row.channel == "push" and row.payload["body"] == "Please settle up when you can."


# ---------- delivery ----------
class FakePush:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def send(self, token, title, body, data):
        if self.fail:
            raise self.fail
        self.sent.append((token, title, body, data))


class FakeEmail:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


def test_deliver_pushes_to_every_device_and_emails_the_rest(client, db_session, abc, clock):
    a, b, c, gid = abc
    db_session.add_all([PushDevice(user_id=uuid.UUID(uid(a)), token="tok-a1"), PushDevice(user_id=uuid.UUID(uid(a)), token="tok-a2")])
    db_session.commit()
    create_group_expense(client, b, gid, equal_body(b, [a, b, c]))
    clock.set(0)
    remind(client, b, a)
    push, email = FakePush(), FakeEmail()
    out = notify.deliver_pending(db_session, push, email)
    assert out == {"sent": 2, "failed": 1, "retry": 0}  # A push (2 devices) + A reminder email sent; C has no device
    assert sorted(t for t, *_ in push.sent) == ["tok-a1", "tok-a2"]
    assert email.sent[0][0] == "asha@example.com" and "Ravi sent you a reminder" in email.sent[0][1]
    statuses = {(r.user_id, r.channel): r.status for r in rows(db_session)}
    assert statuses[(uuid.UUID(uid(c)), "push")] == "failed"
    assert statuses[(uuid.UUID(uid(a)), "push")] == "sent" and all(r.sent_at for r in rows(db_session) if r.status == "sent")
    assert notify.deliver_pending(db_session, push, email) == {"sent": 0, "failed": 0, "retry": 0}  # nothing is sent twice


def test_a_dead_device_token_is_forgotten(client, db_session, abc):
    a, b, c, gid = abc
    db_session.add(PushDevice(user_id=uuid.UUID(uid(a)), token="dead"))
    db_session.commit()
    create_group_expense(client, b, gid, equal_body(b, [a, b, c]))
    notify.deliver_pending(db_session, FakePush(fail=senders.PermanentFailure("gone")), FakeEmail())
    db_session.expire_all()
    assert db_session.scalars(select(PushDevice)).all() == []
    assert pushes(db_session, a)[0].status == "failed"


def test_transient_errors_retry_then_fail_after_three_attempts(client, db_session, abc):
    a, b, c, gid = abc
    db_session.add(PushDevice(user_id=uuid.UUID(uid(a)), token="t"))
    db_session.commit()
    create_group_expense(client, b, gid, equal_body(b, [a, c, b]))
    boom = FakePush(fail=RuntimeError("fcm down"))
    for expected in ({"retry": 1}, {"retry": 1}, {"failed": 1}):
        out = notify.deliver_pending(db_session, boom, FakeEmail())
        for k, v in expected.items():
            assert out[k] >= v
    assert pushes(db_session, a)[0].status == "failed" and pushes(db_session, a)[0].attempts == 3


def test_password_reset_and_invite_emails_are_rendered_and_sent(client, db_session):
    a = user(client, "Asha")
    client.post("/auth/password-reset", json={"email": "asha@example.com"})
    client.post("/groups", json={"name": "Flat", "new_members": [{"name": "Kiran", "email": "kiran@example.com"}]}, headers=h(a))
    email = FakeEmail()
    notify.deliver_pending(db_session, FakePush(), email)
    by_to = {to: (subject, body) for to, subject, body in email.sent}
    assert "Reset your SplitApp password" in by_to["asha@example.com"][0] and "token=pr_" in by_to["asha@example.com"][1]
    assert "Asha invited you" in by_to["kiran@example.com"][0] and "Flat" in by_to["kiran@example.com"][1]


# ---------- real senders (no network, no SMTP server) ----------
def test_fcm_sender_posts_v1_and_maps_errors():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response({"ok": 200, "dead": 404, "down": 503}[json.loads(req.content)["message"]["token"]])

    sender = senders.FcmPushSender("proj-1", lambda: "access-123", httpx.Client(transport=httpx.MockTransport(handler)))
    sender.send("ok", "T", "B", {"entity_id": 5})
    req = seen[0]
    assert str(req.url) == "https://fcm.googleapis.com/v1/projects/proj-1/messages:send"
    assert req.headers["authorization"] == "Bearer access-123"
    assert json.loads(req.content) == {"message": {"token": "ok", "notification": {"title": "T", "body": "B"}, "data": {"entity_id": "5"}}}
    with pytest.raises(senders.PermanentFailure):
        sender.send("dead", "T", "B", {})
    with pytest.raises(RuntimeError):
        sender.send("down", "T", "B", {})


def test_smtp_sender_builds_the_message(monkeypatch):
    log = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): log.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): log.append("starttls")
        def login(self, u, p): log.append(("login", u, p))
        def send_message(self, msg): log.append(("msg", msg["To"], msg["Subject"], msg["From"], msg.get_content().strip()))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    senders.SmtpEmailSender("smtp.test", 587, "u", "p", True, "SplitApp <no-reply@x>").send("a@b.c", "Hi", "Body")
    assert log == [("connect", "smtp.test", 587), "starttls", ("login", "u", "p"),
                   ("msg", "a@b.c", "Hi", "SplitApp <no-reply@x>", "Body")]


def test_default_senders_are_console_and_configuration_selects_real_ones(monkeypatch):
    from app.config import settings
    assert isinstance(senders.get_push_sender(), senders.ConsolePushSender)
    assert isinstance(senders.get_email_sender(), senders.ConsoleEmailSender)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    assert isinstance(senders.get_email_sender(), senders.SmtpEmailSender)
    monkeypatch.setattr(settings, "fcm_project_id", "p")
    monkeypatch.setattr(settings, "fcm_access_token", "tok")
    assert isinstance(senders.get_push_sender(), senders.FcmPushSender)
    monkeypatch.setattr(settings, "fcm_access_token", "")
    with pytest.raises(RuntimeError):
        senders.get_push_sender()
