"""S5-Q-3: business_rules vector 49 (activity unread count) and vector 50 (settlement interleave in the group
timeline). Vector 49 fails before S5-B-3 (GET /activity is 404); vector 50 fails before S5-B-4 and, as the
setup needs settlements, first on POST /settlements (S5-B-2).

Vector 49 seeds activity rows directly (ids increase with created_at so id order and time order agree), which tests the
feed read side on its own; the "one new event by B" step uses the real API and so also needs S5-B-3's expense writes.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, update

from app.models import ActivityLog, ActivityRecipient, User

from tests.expense_helpers import create_group_expense, equal_body, h, make_group, set_created_at, uid, user
from tests.settlement_helpers import pay, set_settlement_created_at
from tests.test_openapi_contract import Caller

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)      # users.activity_last_read_at in vector 49


@pytest.fixture()
def call(client):
    return Caller(client)


# ---- vector 49 ---------------------------------------------------------------------------------------------------

def seed_feed(db, viewer, actor, gid, n_unread=60, n_read=2, in_group=(3, 10, 20, 30, 40)):
    """Wipe the feed, set the viewer's read mark to T0 and insert n_unread newer and n_read older entries."""
    db.execute(delete(ActivityRecipient))
    db.execute(delete(ActivityLog))
    db.execute(update(User).where(User.id == uuid.UUID(uid(viewer))).values(activity_last_read_at=T0))
    stamps = [T0 - timedelta(days=n_read - i) for i in range(n_read)] + \
             [T0 + timedelta(minutes=i + 1) for i in range(n_unread)]                        # ascending
    base = uuid.uuid4().int & ~0xFFFF
    for i, ts in enumerate(stamps):
        act_id = uuid.UUID(int=base + i)
        in_g = (i - n_read) in in_group
        db.add(ActivityLog(id=act_id, actor_id=uuid.UUID(uid(actor)), action="expense.created", entity_type="expense",
                           entity_id=uuid.uuid4(), group_id=uuid.UUID(gid) if in_g else None,
                           payload={"description": f"E{i}", "total": {"amount_minor": 100, "currency": "INR"}},
                           created_at=ts))
        db.flush()
        db.add(ActivityRecipient(activity_id=act_id, user_id=uuid.UUID(uid(viewer)), balance_effect=None))
    db.commit()


def activity(client, who, **params):
    r = client.get("/activity", params=params, headers=h(who))
    assert r.status_code == 200, f"GET /activity -> {r.status_code} (needs S5-B-3): {r.text}"
    return r.json()


@pytest.fixture()
def feed(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    seed_feed(db_session, a, b, gid)
    return {"a": a, "b": b, "gid": gid}


def test_vector_49_unread_count_is_60_on_page_1_page_2_and_the_group_filter(client, feed, call):
    a, gid = feed["a"], feed["gid"]
    tok = a["access_token"]
    p1 = call("GET", "/activity", 200, token=tok, params={"limit": 50}).json()
    assert p1["unread_count"] == 60 and len(p1["items"]) == 50 and all(i["is_unread"] for i in p1["items"])
    assert p1["next_cursor"]
    p2 = call("GET", "/activity", 200, token=tok, params={"limit": 50, "cursor": p1["next_cursor"]}).json()
    assert p2["unread_count"] == 60 and len(p2["items"]) == 12 and p2["next_cursor"] is None
    assert [i["is_unread"] for i in p2["items"]].count(True) == 10 and [i["is_unread"] for i in p2["items"]].count(False) == 2
    assert not {i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]}, "no duplicates across pages"
    filtered = call("GET", "/activity", 200, token=tok, params={"group_id": gid}).json()
    assert len(filtered["items"]) == 5 and all(i["group_id"] == gid for i in filtered["items"])
    assert filtered["unread_count"] == 60, "ignores group_id"


def test_vector_49_unread_count_equals_the_number_of_unread_items_over_the_whole_feed(client, feed):
    a = feed["a"]
    items, cursor = [], None
    for _ in range(10):
        page = activity(client, a, limit=7, **({"cursor": cursor} if cursor else {}))
        assert page["unread_count"] == 60, "not page-limited"
        items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(items) == 62 and len({i["id"] for i in items}) == 62
    assert sum(1 for i in items if i["is_unread"]) == 60


def test_vector_49_default_limit_is_50_and_count_is_not_capped_at_it(client, feed):
    page = activity(client, feed["a"])
    assert len(page["items"]) == 50 and page["unread_count"] == 60


def test_vector_49_null_last_read_counts_everything(client, feed, db_session):
    db_session.execute(update(User).where(User.id == uuid.UUID(uid(feed["a"]))).values(activity_last_read_at=None))
    db_session.commit()
    page = activity(client, feed["a"])
    assert page["unread_count"] == 62 and all(i["is_unread"] for i in page["items"])


def test_vector_49_mark_read_resets_to_zero_then_one_new_event_gives_one(client, feed, call):
    a, b, gid = feed["a"], feed["b"], feed["gid"]
    tok = a["access_token"]
    call("POST", "/activity/read", 204, token=tok)
    p = call("GET", "/activity", 200, token=tok, params={"limit": 100}).json()
    assert p["unread_count"] == 0 and len(p["items"]) == 62 and not any(i["is_unread"] for i in p["items"])
    call("POST", "/activity/read", 204, token=tok)                       # idempotent
    assert activity(client, a)["unread_count"] == 0
    time.sleep(1.1)                                                      # the event must be later than the read mark
    create_group_expense(client, b, gid, equal_body(b, [a, b], total=2000, description="New"))
    after = activity(client, a)
    assert after["unread_count"] == 1
    assert [i["is_unread"] for i in after["items"]].count(True) == 1 and after["items"][0]["is_unread"] is True
    assert after["items"][0]["action"] == "expense.created" and after["items"][0]["group_id"] == gid


def test_vector_49_a_second_users_count_is_independent(client, feed, db_session):
    a, b = feed["a"], feed["b"]
    assert activity(client, b)["unread_count"] == 0 and activity(client, b)["items"] == []   # B has no entries
    r = client.post("/activity/read", headers=h(a))
    assert r.status_code == 204, f"POST /activity/read -> {r.status_code} (needs S5-B-3): {r.text}"
    # give B three entries (dated in the past; B's read mark is null so all are unread); A reading must not have touched B, and B reading must not touch A
    for i in range(3):
        act_id = uuid.uuid4()
        db_session.add(ActivityLog(id=act_id, actor_id=uuid.UUID(uid(a)), action="group.updated", entity_type="group",
                                   entity_id=uuid.UUID(feed["gid"]), group_id=uuid.UUID(feed["gid"]),
                                   payload={"name": "G"}, created_at=datetime.now(timezone.utc) - timedelta(hours=i + 1)))
        db_session.flush()
        db_session.add(ActivityRecipient(activity_id=act_id, user_id=uuid.UUID(uid(b)), balance_effect=None))
    db_session.commit()
    assert activity(client, b)["unread_count"] == 3
    assert activity(client, a)["unread_count"] == 0
    assert client.post("/activity/read", headers=h(b)).status_code == 204
    assert activity(client, b)["unread_count"] == 0


def test_vector_49_unread_count_and_mark_read_require_auth(client):
    assert client.get("/activity").status_code == 401
    assert client.post("/activity/read").status_code == 401


def test_vector_49_group_filter_for_a_foreign_group_shows_none_of_the_callers_entries_for_it(client, feed):
    # the filtered list only contains the caller's own entries for that group; unread_count still the whole feed
    other = user(client, "Zed")
    page = activity(client, other, group_id=feed["gid"])
    assert page["items"] == [] and page["unread_count"] == 0


# ---- vector 50 ---------------------------------------------------------------------------------------------------

def ts(hh, mm=0):
    return datetime(2026, 11, 5, hh, mm, tzinfo=timezone.utc)


@pytest.fixture()
def tl(client, db_session):
    """G = {A, B}, outsider C. E1 11-05 10:00, S1 11-05 12:00, E2 11-06 09:00, S2 11-04 11:00."""
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b])
    e1 = create_group_expense(client, a, gid, equal_body(a, [a, b], description="E1", date="2026-11-05"))
    e2 = create_group_expense(client, a, gid, equal_body(a, [a, b], description="E2", date="2026-11-06"))
    s1 = pay(client, b, b, a, 1000, group_id=gid, settled_on="2026-11-05")
    s2 = pay(client, b, b, a, 500, group_id=gid, settled_on="2026-11-04")
    set_created_at(db_session, e1["id"], ts(10))
    set_created_at(db_session, e2["id"], ts(9))
    set_settlement_created_at(db_session, s1["id"], ts(12))
    set_settlement_created_at(db_session, s2["id"], ts(11))
    return {"a": a, "b": b, "c": c, "gid": gid, "E1": e1["id"], "E2": e2["id"], "S1": s1["id"], "S2": s2["id"]}


def item_id(i):
    assert i["kind"] in ("expense", "settlement")
    return i[i["kind"]]["id"]


def timeline(client, who, gid, **params):
    r = client.get(f"/groups/{gid}/timeline", params=params, headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


def names(tl, body):
    rev = {tl[k]: k for k in ("E1", "E2", "S1", "S2")}
    return [rev[item_id(i)] for i in body["items"]]


def test_vector_50_order_interleaves_expenses_and_settlements(client, tl):
    for who in (tl["a"], tl["b"]):
        body = timeline(client, who, tl["gid"])
        assert names(tl, body) == ["E2", "S1", "E1", "S2"] and body["next_cursor"] is None


def test_vector_50_settlement_items_carry_kind_date_and_the_full_settlement(client, tl):
    body = timeline(client, tl["a"], tl["gid"])
    by = {item_id(i): i for i in body["items"]}
    s1 = by[tl["S1"]]
    assert s1["kind"] == "settlement" and set(s1) == {"kind", "date", "settlement"}
    assert s1["date"] == "2026-11-05" == s1["settlement"]["settled_on"]
    assert s1["settlement"]["amount"] == {"amount_minor": 1000, "currency": "INR"} and s1["settlement"]["group_id"] == tl["gid"]
    assert by[tl["S2"]]["date"] == "2026-11-04"
    assert by[tl["E2"]]["kind"] == "expense" and by[tl["E2"]]["date"] == "2026-11-06"


def test_vector_50_deleted_settlement_hidden_unless_include_deleted(client, tl, call):
    tok = tl["a"]["access_token"]
    assert client.delete(f"/settlements/{tl['S1']}", headers=h(tl["a"])).status_code == 200
    assert names(tl, call("GET", f"/groups/{tl['gid']}/timeline", 200, token=tok).json()) == ["E2", "E1", "S2"]
    shown = call("GET", f"/groups/{tl['gid']}/timeline", 200, token=tok, params={"include_deleted": "true"}).json()
    assert names(tl, shown) == ["E2", "S1", "E1", "S2"]
    flagged = {item_id(i): (i["settlement"] if i["kind"] == "settlement" else i["expense"])["deleted_at"]
               for i in shown["items"]}
    assert flagged[tl["S1"]] is not None and all(v is None for k, v in flagged.items() if k != tl["S1"])
    assert client.post(f"/settlements/{tl['S1']}/restore", headers=h(tl["a"])).status_code == 200
    assert names(tl, timeline(client, tl["a"], tl["gid"])) == ["E2", "S1", "E1", "S2"]


def test_vector_50_limit_2_pages_through_both_kinds(client, tl, call):
    tok = tl["a"]["access_token"]
    assert client.delete(f"/settlements/{tl['S1']}", headers=h(tl["a"])).status_code == 200
    # the vector pages the full (undeleted) order; restore S1 so the pages read [E2, S1] then [E1, S2]
    assert client.post(f"/settlements/{tl['S1']}/restore", headers=h(tl["a"])).status_code == 200
    p1 = call("GET", f"/groups/{tl['gid']}/timeline", 200, token=tok, params={"limit": 2}).json()
    assert names(tl, p1) == ["E2", "S1"] and p1["next_cursor"]
    p2 = call("GET", f"/groups/{tl['gid']}/timeline", 200, token=tok,
              params={"limit": 2, "cursor": p1["next_cursor"]}).json()
    assert names(tl, p2) == ["E1", "S2"] and p2["next_cursor"] is None


def test_vector_50_non_member_is_403_and_unknown_group_404(client, tl, call):
    call("GET", f"/groups/{tl['gid']}/timeline", 403, token=tl["c"]["access_token"])
    call("GET", f"/groups/{uuid.uuid4()}/timeline", 404, token=tl["a"]["access_token"])


def test_vector_50_ties_across_kinds_order_by_id_desc(client, tl, db_session):
    """An expense and a settlement with identical date and created_at: larger id first, whatever the kind."""
    a, b, gid = tl["a"], tl["b"], tl["gid"]
    e = create_group_expense(client, a, gid, equal_body(a, [a, b], description="T", date="2026-11-03"))
    s = pay(client, b, b, a, 300, group_id=gid, settled_on="2026-11-03")
    set_created_at(db_session, e["id"], ts(8))
    set_settlement_created_at(db_session, s["id"], ts(8))
    body = timeline(client, a, gid)
    got = [item_id(i) for i in body["items"]]
    assert got[:4] == [tl["E2"], tl["S1"], tl["E1"], tl["S2"]]
    assert got[4:] == sorted([e["id"], s["id"]], reverse=True)


def test_vector_50_cursor_is_stable_when_items_are_added_between_pages(client, tl, db_session):
    a, b, gid = tl["a"], tl["b"], tl["gid"]
    p1 = timeline(client, a, gid, limit=2)
    newer = pay(client, b, b, a, 100, group_id=gid, settled_on="2026-11-30")      # sorts before everything on page 1
    p2 = timeline(client, a, gid, limit=2, cursor=p1["next_cursor"])
    assert names(tl, p2) == ["E1", "S2"] and p2["next_cursor"] is None
    assert newer["id"] not in [item_id(i) for i in p2["items"]]
    assert item_id(timeline(client, a, gid)["items"][0]) == newer["id"]
