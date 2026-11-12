"""S4-Q-4: business_rules vectors 62-67 (decided 2026-11-11, OQ-43). Tests only; written before S4-B-4.

Old behaviour (Slice 3): only PATCH is blocked for a departed payer/participant; DELETE and restore return 200, a
non-group restore after friend removal returns 200, and GET /groups/{id}/balances is 404 for a soft-deleted group.
New rule: edit, delete and restore of a group expense with a departed payer or participant are 409
EXPENSE_HAS_DEPARTED_MEMBER (after the 404/403 and ALREADY_DELETED/NOT_DELETED checks); rejoining makes them work.
A non-group restore is 409 EXPENSE_HAS_DEPARTED_MEMBER while the participants are not friends.
Vector 66 (settlements) belongs to S5 and is a documented skip.
"""
import uuid

import pytest

from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user

CODE = "EXPENSE_HAS_DEPARTED_MEMBER"


@pytest.fixture()
def w(client):
    a, b, c = (user(client, n) for n in ("Asha", "Ravi", "Meera"))
    gid = make_group(client, a, [b, c])
    return {"a": a, "b": b, "c": c, "gid": gid}


def leave(client, who, gid):
    r = client.delete(f"/groups/{gid}/members/me", headers=h(who))
    assert r.status_code == 204, r.text


def rejoin(client, owner, gid, who):
    r = client.post(f"/groups/{gid}/members", json={"user_ids": [uid(who)]}, headers=h(owner))
    assert r.status_code == 200, r.text


def is_409(r, code=CODE):
    return r.status_code == 409 and r.json()["code"] == code


def snapshot(client, who, gid):
    r = client.get(f"/groups/{gid}/balances", headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


def test_vector_62_delete_and_edit_with_a_departed_participant_are_409(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e1 = create_group_expense(client, a, gid, equal_body(a, [a, b, w["c"]], total=9000))
    create_group_expense(client, b, gid, equal_body(b, [a], total=3000, description="settle"))  # B back at 0
    leave(client, b, gid)
    r = client.delete(f"/expenses/{e1['id']}", headers=h(a))
    assert is_409(r), r.text
    got = client.get(f"/expenses/{e1['id']}", headers=h(a)).json()
    assert got["deleted_at"] is None and got["version"] == e1["version"]
    r = client.patch(f"/expenses/{e1['id']}", json={"version": e1["version"], "description": "x"}, headers=h(a))
    assert is_409(r), r.text


def test_vector_62_departed_payer_blocks_delete_edit_and_restore(client, w):
    a, b, c, gid = w["a"], w["b"], w["c"], w["gid"]
    e = create_group_expense(client, a, gid, equal_body(b, [a, c], total=6000))          # B paid, A and C participate
    gone = create_group_expense(client, a, gid, equal_body(b, [a, c], total=600, description="gone"))
    assert client.delete(f"/expenses/{gone['id']}", headers=h(a)).status_code == 200      # B still a member: fine
    create_group_expense(client, a, gid, equal_body(a, [b], total=6000, description="settle B"))  # B owed 6000 -> 0
    leave(client, b, gid)
    assert is_409(client.delete(f"/expenses/{e['id']}", headers=h(a)))
    assert is_409(client.patch(f"/expenses/{e['id']}", json={"version": e["version"], "description": "x"}, headers=h(a)))
    assert is_409(client.post(f"/expenses/{gone['id']}/restore", headers=h(a)))           # payer departed, restore too
    assert client.get(f"/expenses/{gone['id']}", headers=h(a)).json()["deleted_at"] is not None
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["deleted_at"] is None


def test_vector_62_check_order_not_deleted_and_already_deleted_come_before_the_departed_check(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    live = create_group_expense(client, a, gid, equal_body(a, [a, b], total=6000, description="live"))
    dead = create_group_expense(client, a, gid, equal_body(a, [a, b], total=600, description="dead"))
    assert client.delete(f"/expenses/{dead['id']}", headers=h(a)).status_code == 200
    create_group_expense(client, b, gid, equal_body(b, [a], total=3000, description="settle"))
    leave(client, b, gid)
    r = client.post(f"/expenses/{live['id']}/restore", headers=h(a))
    assert is_409(r, "NOT_DELETED"), r.text                       # NOT_DELETED beats the departed check
    r = client.delete(f"/expenses/{dead['id']}", headers=h(a))
    assert is_409(r, "ALREADY_DELETED"), r.text                   # ALREADY_DELETED beats it too
    # 404 / 403 first
    assert client.delete(f"/expenses/{uuid.uuid4()}", headers=h(a)).status_code == 404
    assert client.delete(f"/expenses/{live['id']}", headers=h(b)).status_code == 403          # B left: not a member


def test_vector_63_restore_with_a_departed_member_is_409(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e1 = create_group_expense(client, a, gid, equal_body(a, [a, b, w["c"]], total=9000))
    before = snapshot(client, a, gid)
    assert client.delete(f"/expenses/{e1['id']}", headers=h(a)).status_code == 200
    leave(client, b, gid)                                                  # B is at 0 with E1 deleted
    mid = snapshot(client, a, gid)
    r = client.post(f"/expenses/{e1['id']}/restore", headers=h(a))
    assert is_409(r), r.text
    assert client.get(f"/expenses/{e1['id']}", headers=h(a)).json()["deleted_at"] is not None
    assert snapshot(client, a, gid) == mid and mid != before              # balances unchanged by the refused restore


def test_vector_64_rejoin_re_enables_restore_and_a_second_departure_blocks_delete_again(client, w):
    a, b, gid = w["a"], w["b"], w["gid"]
    e1 = create_group_expense(client, a, gid, equal_body(a, [a, b, w["c"]], total=9000))
    before = snapshot(client, a, gid)
    assert client.delete(f"/expenses/{e1['id']}", headers=h(a)).status_code == 200
    leave(client, b, gid)
    assert is_409(client.post(f"/expenses/{e1['id']}/restore", headers=h(a)))
    rejoin(client, a, gid, b)
    r = client.post(f"/expenses/{e1['id']}/restore", headers=h(a))
    assert r.status_code == 200 and r.json()["deleted_at"] is None, r.text
    after = snapshot(client, a, gid)
    assert {m["user_id"]: m["balances"] for m in after["members"]} == {m["user_id"]: m["balances"] for m in before["members"]}
    # B owes 3000 again; settle and leave, then DELETE is blocked
    create_group_expense(client, b, gid, equal_body(b, [a], total=3000, description="settle"))
    leave(client, b, gid)
    assert is_409(client.delete(f"/expenses/{e1['id']}", headers=h(a)))
    # rejoin works for edit as well
    rejoin(client, a, gid, b)
    cur = client.get(f"/expenses/{e1['id']}", headers=h(a)).json()
    assert client.patch(f"/expenses/{e1['id']}", json={"version": cur["version"], "description": "ok"},
                        headers=h(a)).status_code == 200


# ---- vector 65: non-group restore after friend removal --------------------------------------------------------------------

@pytest.fixture()
def pair(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    e = create_expense(client, a, equal_body(a, [a, b], total=6000))
    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204       # E soft-deleted with the friendship
    return {"a": a, "b": b, "e": e}


def owed_by_b(client, a, b):
    r = client.get(f"/friends/{uid(b)}", headers=h(a))
    return {x["currency"]: x["amount_minor"] for x in r.json()["balances"] if x["amount_minor"]}


def test_vector_65_restore_after_friend_removal_is_409_until_friends_again(client, pair):
    a, b, e = pair["a"], pair["b"], pair["e"]
    r = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert is_409(r), r.text
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["deleted_at"] is not None
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code in (200, 201)
    r = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert r.status_code == 200 and r.json()["deleted_at"] is None, r.text
    assert owed_by_b(client, a, b) == {"INR": 3000}                                    # B owes A 3000


def test_vector_65_variant_shared_live_group_allows_restore_and_it_survives_group_delete(client, pair):
    a, b, e = pair["a"], pair["b"], pair["e"]
    assert is_409(client.post(f"/expenses/{e['id']}/restore", headers=h(a)))
    gid = make_group(client, a, [b], name="New")
    r = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert r.status_code == 200, r.text
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200       # delete needs no friend check
    assert client.delete(f"/groups/{gid}", headers=h(a)).status_code == 204             # now explicit friends (10.1a)
    r = client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert r.status_code == 200, r.text


def test_vector_65_delete_and_edit_of_a_live_non_group_expense_need_no_friend_check(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    e = create_expense(client, a, equal_body(a, [a, b], total=6000))
    assert client.patch(f"/expenses/{e['id']}", json={"version": 1, "description": "x"}, headers=h(a)).status_code == 200
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200


# ---- vector 67: GET /groups/{id}/balances availability ----------------------------------------------------------------------

def test_vector_67_group_balances_availability(client, w):
    a, b, c, gid = w["a"], w["b"], w["c"], w["gid"]
    outsider = user(client, "Dev")
    r = client.get(f"/groups/{gid}/balances", headers=h(a))
    assert r.status_code == 200 and {"members", "transfers", "simplified"} <= set(r.json())
    r = client.get(f"/groups/{uuid.uuid4()}/balances", headers=h(a))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    assert client.get(f"/groups/{gid}/balances", headers=h(outsider)).status_code == 403
    assert client.get(f"/groups/{gid}/balances").status_code == 401
    leave(client, c, gid)                                                       # C owes nothing, may leave
    assert client.get(f"/groups/{gid}/balances", headers=h(c)).status_code == 403   # a member who left
    create_group_expense(client, a, gid, equal_body(a, [a, b], total=6000))
    live = client.get(f"/groups/{gid}/balances", headers=h(a)).json()
    assert client.delete(f"/groups/{gid}", headers=h(a)).status_code == 204
    r = client.get(f"/groups/{gid}/balances", headers=h(a))                     # soft-deleted group: read-only 200
    assert r.status_code == 200, r.text
    assert r.json() == live
    assert client.get(f"/groups/{gid}/balances", headers=h(outsider)).status_code == 403


@pytest.mark.skip(reason="Vector 66 (settlements with a departed party, non-group restore after friend removal) needs "
                         "the settlements API: runs in S5-Q-1 after S5-B-2")
def test_vector_66_settlement_departed_party_is_409():
    raise AssertionError("S5")
