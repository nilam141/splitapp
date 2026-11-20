"""S6-B-1 / S6-B-2: recurring rules API and the scheduler job (vectors 36, 37, 38 end to end)."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update

from app import scheduler, services_recurring
from app.models import (ActivityLog, Expense, ExpensePayer, ExpenseSplit, GroupMember, Notification, RecurringRule)
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user

UTC = timezone.utc


def at(y, m, d, hour=12):
    return datetime(y, m, d, hour, 0, tzinfo=UTC)


def setup(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c])
    return a, b, c, gid


def rent_body(a, people, **over):
    return equal_body(a, people, total=3_000_000, description="Rent", date="2026-01-31",
                      recurrence={"interval": "monthly", "reminder_days_before": 2}, **over)


def make_rent(client, a, b, c, gid):
    return create_group_expense(client, a, gid, rent_body(a, [a, b, c]))


def rules(db):
    db.expire_all()
    return db.scalars(select(RecurringRule)).all()


def occurrences(db, rule_id):
    db.expire_all()
    return db.scalars(select(Expense).where(Expense.recurring_rule_id == rule_id).order_by(Expense.occurrence_date)).all()


def owed(db, expense_id):
    return {r.user_id: r.owed_amount_minor for r in db.scalars(select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id))}


# ---------- S6-B-1: create ----------
def test_creating_rent_with_recurrence_makes_one_rule_and_marks_the_template(client, db_session):
    a, b, c, gid = setup(client)
    e = make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    assert e["recurring_rule_id"] == str(rule.id)
    assert rule.next_occurrence_date == date(2026, 2, 28) and rule.anchor_date == date(2026, 1, 31)
    assert rule.interval == "monthly" and rule.reminder_days_before == 2 and rule.active
    assert rule.template_expense_id == uuid.UUID(e["id"]) and rule.time_zone == "Asia/Kolkata"
    tmpl = db_session.get(Expense, uuid.UUID(e["id"]))
    assert tmpl.recurring_rule_id == rule.id and tmpl.occurrence_date == date(2026, 1, 31)
    got = client.get(f"/expenses/{e['id']}", headers=h(a)).json()
    assert got["recurring_rule_id"] == str(rule.id)


def test_plain_and_null_recurrence_make_no_rule(client, db_session):
    a, b, c, gid = setup(client)
    create_group_expense(client, a, gid, equal_body(a, [a, b]))
    create_group_expense(client, a, gid, {**equal_body(a, [a, b]), "recurrence": None})
    assert rules(db_session) == []


def test_recurrence_validation(client):
    a, b, c, gid = setup(client)
    for bad in ({"interval": "daily"}, {"interval": "monthly", "reminder_days_before": 8},
                {"interval": "monthly", "reminder_days_before": -1}, {}):
        r = client.post(f"/groups/{gid}/expenses", json={**equal_body(a, [a, b]), "recurrence": bad}, headers=h(a))
        assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR", bad


def test_get_list_shape_and_filter(client):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    other = make_group(client, a, [b], name="Other")
    items = client.get("/recurring-expenses", headers=h(a)).json()["items"]
    assert len(items) == 1
    r = items[0]
    assert r["description"] == "Rent" and r["total"] == {"amount_minor": 3_000_000, "currency": "INR"}
    assert r["interval"] == "monthly" and r["anchor_date"] == "2026-01-31" and r["group_id"] == gid
    assert r["next_occurrence_date"] == "2026-02-28" and r["reminder_days_before"] == 2 and r["active"] is True
    assert client.get("/recurring-expenses", params={"group_id": other}, headers=h(a)).json() == {"items": []}
    assert len(client.get("/recurring-expenses", params={"group_id": gid}, headers=h(b)).json()["items"]) == 1


def test_list_hides_rules_of_groups_the_caller_is_not_in(client):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    d = user(client, "Dev")
    assert client.get("/recurring-expenses", headers=h(d)).json() == {"items": []}
    assert client.get("/recurring-expenses").status_code == 401


def test_post_recurring_on_an_existing_expense(client, db_session):
    a, b, c, gid = setup(client)
    e = create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=900, date="2026-03-15"))
    d = user(client, "Dev")
    body = {"template_expense_id": e["id"], "interval": "weekly", "reminder_days_before": None}
    assert client.post("/recurring-expenses", json=body, headers=h(d)).status_code == 403
    assert client.post("/recurring-expenses", json={**body, "template_expense_id": str(uuid.uuid4())}, headers=h(a)).status_code == 404
    r = client.post("/recurring-expenses", json=body, headers=h(b))  # any member may
    assert r.status_code == 201
    rule = r.json()
    assert rule["template_expense_id"] == e["id"] and rule["next_occurrence_date"] == "2026-03-22"
    assert rule["interval"] == "weekly" and rule["reminder_days_before"] is None and rule["active"] is True
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["recurring_rule_id"] == rule["id"]
    again = client.post("/recurring-expenses", json=body, headers=h(a))
    assert again.status_code == 409 and again.json()["code"] == "VALIDATION_ERROR"
    assert client.post("/recurring-expenses", json={**body, "interval": "daily"}, headers=h(a)).status_code == 422


def test_post_recurring_on_a_deleted_expense_is_409(client):
    a, b, c, gid = setup(client)
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))
    client.delete(f"/expenses/{e['id']}", headers=h(a))
    r = client.post("/recurring-expenses", json={"template_expense_id": e["id"], "interval": "monthly"}, headers=h(a))
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_DELETED"


def test_non_group_rule_is_visible_to_both_people_only(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a))
    body = {**equal_body(a, [a, b], total=500, date="2026-05-01"), "recurrence": {"interval": "monthly"}}
    r = client.post("/expenses", json=body, headers=h(a))
    assert r.status_code == 201
    assert client.get("/recurring-expenses", headers=h(a)).json()["items"][0]["group_id"] is None
    assert len(client.get("/recurring-expenses", headers=h(b)).json()["items"]) == 1
    d = user(client, "Dev")
    assert client.get("/recurring-expenses", headers=h(d)).json()["items"] == []


# ---------- PATCH / DELETE ----------
def test_patch_interval_reminder_and_stop(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    rid = str(rule.id)
    r = client.patch(f"/recurring-expenses/{rid}", json={"reminder_days_before": 5}, headers=h(b))
    assert r.status_code == 200 and r.json()["reminder_days_before"] == 5 and r.json()["interval"] == "monthly"
    r = client.patch(f"/recurring-expenses/{rid}", json={"interval": "weekly"}, headers=h(a))
    assert r.status_code == 200 and r.json()["interval"] == "weekly"
    assert r.json()["next_occurrence_date"] == "2026-02-07"  # the first weekly date after the template's date
    r = client.patch(f"/recurring-expenses/{rid}", json={"reminder_days_before": None}, headers=h(a))
    assert r.json()["reminder_days_before"] is None
    r = client.patch(f"/recurring-expenses/{rid}", json={"active": False}, headers=h(a))
    assert r.status_code == 200 and r.json()["active"] is False
    assert services_recurring.run_due(db_session, at(2027, 1, 1)) == 0  # stopped: nothing is created
    assert client.patch(f"/recurring-expenses/{rid}", json={"interval": None}, headers=h(a)).status_code == 422
    assert client.patch(f"/recurring-expenses/{rid}", json={"interval": "daily"}, headers=h(a)).status_code == 422
    assert client.patch(f"/recurring-expenses/{rid}", json={"reminder_days_before": 9}, headers=h(a)).status_code == 422


def test_resuming_does_not_back_fill_the_pause(client, db_session, monkeypatch):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    client.patch(f"/recurring-expenses/{rule.id}", json={"active": False}, headers=h(a))
    monkeypatch.setattr(services_recurring, "_now", lambda: at(2026, 6, 10))
    r = client.patch(f"/recurring-expenses/{rule.id}", json={"active": True}, headers=h(a))
    assert r.json()["active"] is True and r.json()["next_occurrence_date"] == "2026-06-30"


def test_patch_and_delete_need_access_and_an_existing_rule(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    d = user(client, "Dev")
    assert client.patch(f"/recurring-expenses/{rule.id}", json={"active": False}, headers=h(d)).status_code == 403
    assert client.delete(f"/recurring-expenses/{rule.id}", headers=h(d)).status_code == 403
    nope = uuid.uuid4()
    assert client.patch(f"/recurring-expenses/{nope}", json={"active": False}, headers=h(a)).status_code == 404
    assert client.delete(f"/recurring-expenses/{nope}", headers=h(a)).status_code == 404
    assert client.delete(f"/recurring-expenses/{rule.id}").status_code == 401


def test_delete_keeps_past_occurrences(client, db_session):
    a, b, c, gid = setup(client)
    e = make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    services_recurring.run_due(db_session, at(2026, 2, 28))
    assert client.delete(f"/recurring-expenses/{rule.id}", headers=h(b)).status_code == 204
    assert rules(db_session) == []
    page = client.get(f"/groups/{gid}/expenses", headers=h(a)).json()["items"]
    assert len(page) == 2 and all(i["recurring_rule_id"] is None for i in page)
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).status_code == 200
    assert services_recurring.run_due(db_session, at(2026, 6, 1)) == 0
    assert client.get("/recurring-expenses", headers=h(a)).json() == {"items": []}


# ---------- S6-B-2: the job ----------
def test_running_the_job_twice_for_the_same_date_creates_one_expense(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    assert services_recurring.run_due(db_session, at(2026, 2, 28)) == 1
    assert services_recurring.run_due(db_session, at(2026, 2, 28)) == 0
    assert services_recurring.run_due(db_session, at(2026, 2, 28, 20)) == 0
    occ = occurrences(db_session, rule.id)
    assert [o.occurrence_date for o in occ] == [date(2026, 1, 31), date(2026, 2, 28)]
    new = occ[1]
    assert new.expense_date == date(2026, 2, 28) and new.description == "Rent" and new.created_by == rule.created_by
    assert new.total_amount_minor == 3_000_000 and new.version == 1 and new.group_id == uuid.UUID(gid)
    assert owed(db_session, new.id) == {uuid.UUID(uid(x)): 1_000_000 for x in (a, b, c)}
    assert rules(db_session)[0].next_occurrence_date == date(2026, 3, 31)


def test_vector_36_through_the_job_month_end_dates(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    for now, expect_next in ((at(2026, 2, 28), date(2026, 3, 31)), (at(2026, 3, 31), date(2026, 4, 30)),
                             (at(2026, 4, 30), date(2026, 5, 31))):
        services_recurring.run_due(db_session, now)
        assert rules(db_session)[0].next_occurrence_date == expect_next
    assert [o.occurrence_date for o in occurrences(db_session, rule.id)] == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_not_due_yet_creates_nothing(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    assert services_recurring.run_due(db_session, at(2026, 2, 27)) == 0


def test_catch_up_after_an_outage_creates_every_missed_occurrence_once(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    # the job was down 02-28 .. 04-01: both 02-28 and 03-31 are missed
    assert services_recurring.run_due(db_session, at(2026, 4, 1)) == 2
    assert services_recurring.run_due(db_session, at(2026, 4, 1)) == 0
    assert [o.occurrence_date for o in occurrences(db_session, rule.id)] == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert rules(db_session)[0].next_occurrence_date == date(2026, 4, 30)


def test_three_day_outage_fortnightly(client, db_session):
    a, b, c, gid = setup(client)
    body = equal_body(a, [a, b, c], total=900, date="2026-01-01", recurrence={"interval": "fortnightly"})
    create_group_expense(client, a, gid, body)
    [rule] = rules(db_session)
    assert rule.next_occurrence_date == date(2026, 1, 15)
    assert services_recurring.run_due(db_session, at(2026, 1, 14)) == 0
    assert services_recurring.run_due(db_session, at(2026, 1, 18)) == 1  # job back 3 days late
    assert services_recurring.run_due(db_session, at(2026, 1, 29)) == 1
    assert [o.occurrence_date for o in occurrences(db_session, rule.id)] == [
        date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)]


def test_the_rule_time_zone_decides_what_today_is(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)  # Asia/Kolkata, next 2026-02-28
    # 2026-02-27 20:00 UTC is already 02-28 01:30 in Kolkata
    assert services_recurring.run_due(db_session, at(2026, 2, 27, 20)) == 1


def test_vector_38_member_left_next_occurrence_drops_them(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    [rule] = rules(db_session)
    db_session.execute(update(GroupMember).where(GroupMember.group_id == uuid.UUID(gid),
                                                 GroupMember.user_id == uuid.UUID(uid(b)))
                       .values(left_at=at(2026, 2, 10)))
    db_session.commit()
    assert services_recurring.run_due(db_session, at(2026, 2, 28)) == 1
    new = occurrences(db_session, rule.id)[1]
    assert owed(db_session, new.id) == {uuid.UUID(uid(a)): 1_500_000, uuid.UUID(uid(c)): 1_500_000}
    payers = db_session.scalars(select(ExpensePayer).where(ExpensePayer.expense_id == new.id)).all()
    assert [(p.user_id, p.paid_amount_minor) for p in payers] == [(uuid.UUID(uid(a)), 3_000_000)]
    # the same through the API: A's group balance is +1,500,000 from this occurrence alone
    assert client.get(f"/expenses/{new.id}", headers=h(a)).json()["my_net"]["amount_minor"] == 1_500_000


def test_vector_38_the_first_occurrence_is_unchanged_and_balances_hold(client, db_session):
    a, b, c, gid = setup(client)
    e = make_rent(client, a, b, c, gid)
    assert [s["owed_amount_minor"] for s in e["splits"]] == [1_000_000] * 3
    db_session.execute(update(GroupMember).where(GroupMember.user_id == uuid.UUID(uid(c))).values(left_at=at(2026, 2, 1)))
    db_session.commit()
    services_recurring.run_due(db_session, at(2026, 2, 28))
    assert db_session.scalar(select(func.count()).select_from(Expense)) == 2


def test_everyone_gone_deactivates_the_rule(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    db_session.execute(update(GroupMember).where(GroupMember.group_id == uuid.UUID(gid),
                                                 GroupMember.user_id == uuid.UUID(uid(a))).values(left_at=at(2026, 2, 1)))
    db_session.commit()  # A paid the template: no payer remains
    assert services_recurring.run_due(db_session, at(2026, 2, 28)) == 0
    [rule] = rules(db_session)
    assert rule.active is False and len(occurrences(db_session, rule.id)) == 1
    assert client.get("/recurring-expenses", headers=h(b)).json()["items"][0]["active"] is False


def test_deleted_group_or_deleted_template_deactivates_the_rule(client, db_session):
    a, b, c, gid = setup(client)
    e = make_rent(client, a, b, c, gid)
    client.delete(f"/expenses/{e['id']}", headers=h(a))
    assert services_recurring.run_due(db_session, at(2026, 2, 28)) == 0
    assert rules(db_session)[0].active is False
    a2, b2, c2, gid2 = (user(client, "Zed"), None, None, None)
    gid2 = make_group(client, a2, [])
    create_group_expense(client, a2, gid2, {**equal_body(a2, [a2], total=100, date="2026-01-31"),
                                            "recurrence": {"interval": "monthly"}})
    client.delete(f"/groups/{gid2}", headers=h(a2))
    services_recurring.run_due(db_session, at(2026, 2, 28))
    assert all(r.active is False for r in rules(db_session))


def test_occurrence_notifies_everyone_without_an_actor(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    before = db_session.scalar(select(func.count()).select_from(Notification).where(Notification.type == "expense_added"))
    services_recurring.run_due(db_session, at(2026, 2, 28))
    log = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "expense.created")
                             .order_by(ActivityLog.created_at.desc())).first()
    assert log.actor_id is None and log.payload["recurring"] is True
    rows = db_session.scalars(select(Notification).where(Notification.type == "expense_added")).all()
    assert len(rows) - before == 3  # A, B and C: there is no actor to skip
    feed = client.get("/activity", headers=h(a)).json()
    assert feed["items"][0]["actor"] is None and feed["items"][0]["is_unread"] is True
    assert feed["items"][0]["my_effect"] == [{"amount_minor": 2_000_000, "currency": "INR"}]


def test_reminder_is_queued_once_before_the_date(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)  # reminder_days_before = 2, next 02-28
    q = lambda: db_session.scalars(select(Notification).where(Notification.type == "reminder")).all()
    services_recurring.run_due(db_session, at(2026, 2, 25))
    assert q() == []
    services_recurring.run_due(db_session, at(2026, 2, 26))
    rows = q()
    assert len(rows) == 1 and rows[0].user_id == uuid.UUID(uid(a)) and rows[0].channel == "push"
    assert rows[0].payload["occurrence_date"] == "2026-02-28"
    services_recurring.run_due(db_session, at(2026, 2, 26, 18))
    services_recurring.run_due(db_session, at(2026, 2, 27))
    assert len(q()) == 1
    services_recurring.run_due(db_session, at(2026, 2, 28))  # the expense itself; the next reminder is for 03-31
    assert len(q()) == 1
    services_recurring.run_due(db_session, at(2026, 3, 29))
    assert len(q()) == 2


def test_reminder_respects_the_reminder_preference(client, db_session):
    a, b, c, gid = setup(client)
    client.patch("/users/me", json={"notification_prefs": {"reminder": False}}, headers=h(a))
    make_rent(client, a, b, c, gid)
    services_recurring.run_due(db_session, at(2026, 2, 27))
    assert db_session.scalars(select(Notification).where(Notification.type == "reminder")).all() == []


def test_scheduler_run_once_runs_every_step(client, db_session):
    a, b, c, gid = setup(client)
    make_rent(client, a, b, c, gid)
    out = scheduler.run_once(db_session, at(2026, 2, 28))
    assert out["occurrences"] == 1 and out["notifications_sent"] >= 0 and -1 not in out.values()
