"""S6-B-4: invite links, joining, claiming a placeholder, and adding a friend by code."""
import uuid

import pytest
from sqlalchemy import select, update

from app.config import settings
from app.models import (ActivityLog, Comment, Expense, ExpensePayer, ExpenseSplit, Friendship, GroupInvite, GroupMember,
                        Settlement, User)
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user


def link(client, who, gid):
    r = client.get(f"/groups/{gid}/invite-link", headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


def join(client, who, token, **extra):
    return client.post("/groups/join", json={"token": token, **extra}, headers=h(who))


@pytest.fixture()
def ab(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    return a, b, make_group(client, a, [b])


# ---------- the link ----------
def test_get_creates_once_and_returns_the_same_token(client, db_session, ab):
    a, b, gid = ab
    first = link(client, a, gid)
    assert set(first) == {"token", "url"} and first["url"] == settings.invite_base_url.rstrip("/") + "/" + first["token"]
    assert len(first["token"]) <= 32 and first["token"].isascii()
    assert link(client, b, gid) == first  # any member sees the same active link
    db_session.expire_all()
    assert len(db_session.scalars(select(GroupInvite)).all()) == 1


def test_link_needs_membership_and_a_live_group(client, ab):
    a, b, gid = ab
    d = user(client, "Dev")
    assert client.get(f"/groups/{gid}/invite-link", headers=h(d)).status_code == 403
    assert client.post(f"/groups/{gid}/invite-link", headers=h(d)).status_code == 403
    assert client.get(f"/groups/{uuid.uuid4()}/invite-link", headers=h(a)).status_code == 404
    assert client.get(f"/groups/{gid}/invite-link").status_code == 401
    client.delete(f"/groups/{gid}", headers=h(a))
    assert client.get(f"/groups/{gid}/invite-link", headers=h(a)).status_code == 409


def test_a_reset_link_the_old_token_gives_410(client, db_session, ab):
    a, b, gid = ab
    d = user(client, "Dev")
    old = link(client, a, gid)
    r = client.post(f"/groups/{gid}/invite-link", headers=h(b))
    assert r.status_code == 201 and r.json()["token"] != old["token"]
    new = r.json()
    j = join(client, d, old["token"])
    assert j.status_code == 410 and j.json()["code"] == "LINK_EXPIRED"
    assert link(client, a, gid) == new
    assert join(client, d, new["token"]).status_code == 200
    db_session.expire_all()
    inv = db_session.scalars(select(GroupInvite)).all()
    assert len(inv) == 2 and sum(i.revoked_at is None for i in inv) == 1


# ---------- joining ----------
def test_join_adds_the_member_and_notifies_the_group(client, db_session, ab):
    a, b, gid = ab
    d = user(client, "Dev")
    r = join(client, d, link(client, a, gid)["token"])
    assert r.status_code == 200
    g = r.json()
    assert gid == g["id"] and {m["user"]["name"] for m in g["members"]} == {"Asha", "Ravi", "Dev"}
    assert [x["id"] for x in client.get("/groups", headers=h(d)).json()["items"]] == [gid]
    db_session.expire_all()
    log = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "group.member_added")).all()[-1]
    assert log.actor_id == uuid.UUID(uid(d)) and log.payload["user_id"] == uid(d)
    d_row = db_session.get(GroupMember, (uuid.UUID(gid), uuid.UUID(uid(d))))
    assert d_row.sort_index == 2 and d_row.left_at is None
    # a new member can use the group
    assert create_group_expense(client, d, gid, equal_body(d, [a, b, d]))["created_by"] == uid(d)


def test_joining_twice_changes_nothing(client, db_session, ab):
    a, b, gid = ab
    token = link(client, a, gid)["token"]
    assert join(client, b, token).status_code == 200  # already a member
    d = user(client, "Dev")
    join(client, d, token)
    assert join(client, d, token).status_code == 200
    db_session.expire_all()
    assert len(db_session.scalars(select(GroupMember).where(GroupMember.group_id == uuid.UUID(gid))).all()) == 3


def test_a_member_who_left_can_rejoin(client, db_session, ab):
    a, b, gid = ab
    token = link(client, a, gid)["token"]
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    assert join(client, b, token).status_code == 200
    db_session.expire_all()
    assert db_session.get(GroupMember, (uuid.UUID(gid), uuid.UUID(uid(b)))).left_at is None
    assert len([m for m in client.get(f"/groups/{gid}", headers=h(a)).json()["members"] if m["left_at"] is None]) == 2


def test_bad_deleted_and_unauthenticated_joins(client, ab):
    a, b, gid = ab
    d = user(client, "Dev")
    for token in ("nope", "  ", "x" * 40):
        r = join(client, d, token)
        assert r.status_code in (410, 422), token
        if r.status_code == 410:
            assert r.json()["code"] == "LINK_EXPIRED"
    token = link(client, a, gid)["token"]
    assert client.post("/groups/join", json={"token": token}).status_code == 401
    assert client.post("/groups/join", json={}, headers=h(d)).status_code == 422
    client.delete(f"/groups/{gid}", headers=h(a))
    assert join(client, d, token).status_code == 410


def test_a_full_group_refuses_a_new_member(client, db_session, ab):
    a, b, gid = ab
    token = link(client, a, gid)["token"]
    for i in range(198):  # 2 real members + 198 placeholders = the 200 cap
        p = User(id=uuid.uuid4(), name=f"P{i}", is_registered=False, default_currency="INR", notification_prefs={},
                 friend_code=uuid.uuid4().hex[:12])
        db_session.add(p)
        db_session.flush()
        db_session.add(GroupMember(group_id=uuid.UUID(gid), user_id=p.id, sort_index=10 + i))
    db_session.commit()
    d = user(client, "Dev")
    r = join(client, d, token)
    assert r.status_code == 422 and r.json()["code"] == "GROUP_TOO_LARGE"


# ---------- claiming a placeholder ----------
@pytest.fixture()
def kiran_group(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    g = client.post("/groups", json={"name": "Flat", "member_user_ids": [uid(b)],
                                     "new_members": [{"name": "Kiran", "email": "kiran@example.com"}]},
                    headers=h(a)).json()
    kiran = next(m["user"]["id"] for m in g["members"] if m["user"]["name"] == "Kiran")
    return a, b, g["id"], kiran


def split_body(payer, total, entries, **extra):
    return {"description": "Dinner", "total": {"amount_minor": total, "currency": "INR"}, "expense_date": "2026-11-05",
            "payers": [{"user_id": payer, "paid_amount_minor": total}],
            "split": {"type": "equal", "entries": [{"user_id": u} for u in entries]}, **extra}


def test_claiming_a_placeholder_moves_all_of_kirans_rows_to_the_joining_user(client, db_session, kiran_group):
    a, b, gid, kiran = kiran_group
    e1 = create_group_expense(client, a, gid, split_body(uid(a), 9000, [uid(a), uid(b), kiran]))
    e2 = create_group_expense(client, a, gid, {**split_body(uid(a), 600, [uid(a), kiran]),
                                               "split": {"type": "exact", "entries": [{"user_id": uid(a), "value": 100}, {"user_id": kiran, "value": 500}]}})
    e3 = create_group_expense(client, a, gid, {**split_body(kiran, 3000, [uid(a), uid(b), kiran]),
                                               "payers": [{"user_id": kiran, "paid_amount_minor": 3000}]})
    d = user(client, "Dev")
    kiran_net = next(m["balances"] for m in client.get(f"/groups/{gid}/balances", headers=h(a)).json()["members"] if m["user_id"] == kiran)
    assert kiran_net
    r = join(client, d, link(client, a, gid)["token"], claim_placeholder_user_id=kiran)
    assert r.status_code == 200
    members = {m["user"]["id"]: m for m in r.json()["members"]}
    assert kiran not in members and uid(d) in members and len(members) == 3
    db_session.expire_all()
    dev, kir = uuid.UUID(uid(d)), uuid.UUID(kiran)
    assert db_session.scalars(select(ExpenseSplit).where(ExpenseSplit.user_id == kir)).all() == []
    assert db_session.scalars(select(ExpensePayer).where(ExpensePayer.user_id == kir)).all() == []
    d_splits = {s.expense_id: s.owed_amount_minor for s in db_session.scalars(select(ExpenseSplit).where(ExpenseSplit.user_id == dev))}
    assert d_splits == {uuid.UUID(e1["id"]): 3000, uuid.UUID(e2["id"]): 500, uuid.UUID(e3["id"]): 1000}
    assert [p.paid_amount_minor for p in db_session.scalars(select(ExpensePayer).where(ExpensePayer.user_id == dev))] == [3000]
    # every expense still adds up
    for e in db_session.scalars(select(Expense)):
        assert sum(p.paid_amount_minor for p in db_session.scalars(select(ExpensePayer).where(ExpensePayer.expense_id == e.id))) == e.total_amount_minor
        assert sum(s.owed_amount_minor for s in db_session.scalars(select(ExpenseSplit).where(ExpenseSplit.expense_id == e.id))) == e.total_amount_minor
    # Dev took Kiran's seat (the canonical order of future splits stays put) and Kiran is retired
    assert db_session.get(GroupMember, (uuid.UUID(gid), dev)).sort_index == 2
    k = db_session.get(User, kir)
    assert k.merged_into == dev and k.deleted_at is not None and k.email is None
    # balances belong to Dev now: same numbers as Kiran had
    mine = next(m["balances"] for m in client.get(f"/groups/{gid}/balances", headers=h(a)).json()["members"] if m["user_id"] == uid(d))
    assert mine == kiran_net  # Dev now carries exactly what Kiran carried
    got = client.get(f"/expenses/{e1['id']}", headers=h(d)).json()
    assert got["my_net"]["amount_minor"] == -3000


def test_claim_by_a_member_who_is_already_on_the_same_expense_sums_the_rows(client, db_session, kiran_group):
    a, b, gid, kiran = kiran_group
    d = user(client, "Dev")
    token = link(client, a, gid)["token"]
    assert join(client, d, token).status_code == 200
    e = create_group_expense(client, a, gid, split_body(uid(a), 9000, [uid(a), uid(d), kiran]))
    assert join(client, d, token, claim_placeholder_user_id=kiran).status_code == 200
    db_session.expire_all()
    rows = db_session.scalars(select(ExpenseSplit).where(ExpenseSplit.expense_id == uuid.UUID(e["id"]))).all()
    assert len(rows) == 2 and sum(r.owed_amount_minor for r in rows) == 9000
    assert {r.user_id: r.owed_amount_minor for r in rows}[uuid.UUID(uid(d))] == 6000
    members = client.get(f"/groups/{gid}", headers=h(a)).json()["members"]
    assert sorted(m["user"]["name"] for m in members if m["left_at"] is None) == ["Asha", "Dev", "Ravi"]


def test_claim_repoints_settlements_comments_and_friendships(client, db_session, kiran_group):
    a, b, gid, kiran = kiran_group
    e = create_group_expense(client, a, gid, split_body(uid(a), 9000, [uid(a), uid(b), kiran]))
    pay = {"group_id": gid, "from_user_id": kiran, "to_user_id": uid(a), "amount": {"amount_minor": 1000, "currency": "INR"}, "settled_on": "2026-11-06"}
    s = client.post("/settlements", json=pay, headers=h(a))
    assert s.status_code == 201, s.text
    db_session.add(Comment(id=uuid.uuid4(), expense_id=uuid.UUID(e["id"]), user_id=uuid.UUID(kiran), kind="user", body="hi"))
    db_session.commit()
    d = user(client, "Dev")
    assert join(client, d, link(client, a, gid)["token"], claim_placeholder_user_id=kiran).status_code == 200
    db_session.expire_all()
    dev = uuid.UUID(uid(d))
    st = db_session.scalars(select(Settlement)).all()[0]
    assert st.from_user_id == dev and st.to_user_id == uuid.UUID(uid(a))
    assert db_session.scalars(select(Comment).where(Comment.user_id == uuid.UUID(kiran))).all() == []
    assert client.get("/settlements", headers=h(d)).json()["items"][0]["id"] == s.json()["id"]
    friends = {f["user"]["id"] for f in client.get("/friends", headers=h(d)).json()["items"]}
    assert friends == {uid(a), uid(b)}  # through the shared group; the placeholder is gone from every list
    assert kiran not in {f["user"]["id"] for f in client.get("/friends", headers=h(a)).json()["items"]}


def test_claim_merges_an_explicit_friendship(client, db_session, kiran_group):
    a, b, gid, kiran = kiran_group
    d = user(client, "Dev")
    client.post("/friends", json={"email": "dev@example.com"}, headers=h(a))  # A already friends with Dev
    client.post("/friends", json={"friend_code": db_session.get(User, uuid.UUID(kiran)).friend_code}, headers=h(a))
    join(client, d, link(client, a, gid)["token"], claim_placeholder_user_id=kiran)
    db_session.expire_all()
    pairs = db_session.scalars(select(Friendship)).all()
    ids = {(f.user_id, f.friend_id) for f in pairs}
    assert len(ids) == len(pairs)  # no duplicate pair, ordering constraint held
    assert all(f.user_id < f.friend_id for f in pairs)
    kir = uuid.UUID(kiran)
    assert not any(kir in p for p in ids)


def test_claim_validation(client, kiran_group):
    a, b, gid, kiran = kiran_group
    d = user(client, "Dev")
    token = link(client, a, gid)["token"]
    other = client.post("/groups", json={"name": "Other", "new_members": [{"name": "Zed", "email": "zed@example.com"}]}, headers=h(a)).json()
    zed = next(m["user"]["id"] for m in other["members"] if m["user"]["name"] == "Zed")
    for bad in (uid(b), zed, str(uuid.uuid4()), uid(d)):
        r = join(client, d, token, claim_placeholder_user_id=bad)
        assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR", bad
    assert join(client, d, token, claim_placeholder_user_id=None).status_code == 200
    assert join(client, user(client, "Eve"), token, claim_placeholder_user_id="not-a-uuid").status_code == 422
    # a failed claim joins nobody
    f = user(client, "Fay")
    assert join(client, f, token, claim_placeholder_user_id=str(uuid.uuid4())).status_code == 422
    assert uid(f) not in {m["user"]["id"] for m in client.get(f"/groups/{gid}", headers=h(a)).json()["members"]}


def test_a_claimed_placeholder_cannot_be_claimed_again(client, kiran_group):
    a, b, gid, kiran = kiran_group
    token = link(client, a, gid)["token"]
    assert join(client, user(client, "Dev"), token, claim_placeholder_user_id=kiran).status_code == 200
    assert join(client, user(client, "Eve"), token, claim_placeholder_user_id=kiran).status_code == 422


# ---------- friend code ----------
def code_of(db_session, u):
    db_session.expire_all()
    return db_session.get(User, uuid.UUID(uid(u))).friend_code


def test_add_friend_by_code(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    code = code_of(db_session, b)
    r = client.post("/friends", json={"friend_code": code.lower()}, headers=h(a))  # case-insensitive
    assert r.status_code == 201 and r.json()["friend"]["user"]["id"] == uid(b) and r.json()["is_new_user"] is False
    assert client.post("/friends", json={"friend_code": code}, headers=h(a)).status_code == 200
    assert [f["user"]["id"] for f in client.get("/friends", headers=h(b)).json()["items"]] == [uid(a)]


def test_a_reset_friend_code_gives_410(client, db_session):
    a, b = user(client, "Asha"), user(client, "Ravi")
    old = code_of(db_session, b)
    db_session.execute(update(User).where(User.id == uuid.UUID(uid(b))).values(friend_code="NEWCODE99"))
    db_session.commit()
    r = client.post("/friends", json={"friend_code": old}, headers=h(a))
    assert r.status_code == 410 and r.json()["code"] == "LINK_EXPIRED"
    assert client.post("/friends", json={"friend_code": "NEWCODE99"}, headers=h(a)).status_code == 201
    assert client.post("/friends", json={"friend_code": "NOSUCHCODE"}, headers=h(a)).status_code == 410


def test_friend_code_edge_cases(client, db_session):
    a = user(client, "Asha")
    r = client.post("/friends", json={"friend_code": code_of(db_session, a)}, headers=h(a))
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_FRIEND_SELF"
    assert client.post("/friends", json={"friend_code": "ABC", "email": "x@example.com"}, headers=h(a)).status_code == 422
