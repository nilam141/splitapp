"""S3-Q-4: business_rules vectors 41 (expense half) and 42. Written before S3-B-4, so they fail until it ships.

Setup needs S3-B-3 (create expenses); until that exists the setup assertion fails with the POST status (404/405).
Vector 41 settlement half belongs to S5-Q-1.
"""
import uuid

from sqlalchemy import select

from tests.expense_helpers import (create_expense, create_group_expense, equal_body, expenses_table, h, make_group,
                                   uid, user)


def _group_with_expense(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b], total=10000))
    return a, b, gid, e


# ---- vector 41 ---------------------------------------------------------------------------------------------------

def test_vector_41_patch_with_other_currency_is_422_and_changes_nothing(client):
    a, b, gid, e = _group_with_expense(client)
    assert e["total"] == {"amount_minor": 10000, "currency": "INR"} and e["version"] == 1
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 10000, "currency": "USD"}},
                     headers=h(a))
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["fields"][0]["field"] == "total.currency"
    after = client.get(f"/expenses/{e['id']}", headers=h(a))
    assert after.status_code == 200
    assert after.json() == e  # expense unchanged, version still 1, no updated_at/updated_by bump
    assert after.json()["version"] == 1


def test_vector_41_other_currency_with_a_new_amount_is_still_rejected(client):
    a, b, gid, e = _group_with_expense(client)
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 99, "currency": "USD"}},
                     headers=h(a))
    assert r.status_code == 422 and r.json()["details"]["fields"][0]["field"] == "total.currency"
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json() == e


def test_vector_41_same_currency_with_a_new_amount_succeeds(client):
    a, b, gid, e = _group_with_expense(client)
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 12000, "currency": "INR"}},
                     headers=h(a))
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["total"] == {"amount_minor": 12000, "currency": "INR"}
    assert got["version"] == 2
    # features.md (edit flow): editing the amount of an equal expense re-splits it (9000 -> 12000 gives 4000 x 3)
    assert [s["owed_amount_minor"] for s in got["splits"]] == [6000, 6000]
    assert sum(p["paid_amount_minor"] for p in got["payers"]) == 12000
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["version"] == 2


def test_vector_41_same_currency_with_payers_and_split_succeeds(client):
    a, b, gid, e = _group_with_expense(client)
    body = {"version": 1, "total": {"amount_minor": 3000, "currency": "INR"},
            "payers": [{"user_id": uid(a), "paid_amount_minor": 3000}],
            "split": {"type": "exact", "entries": [{"user_id": uid(a), "value": 1000}, {"user_id": uid(b), "value": 2000}]}}
    r = client.patch(f"/expenses/{e['id']}", json=body, headers=h(a))
    assert r.status_code == 200, r.text
    assert [s["owed_amount_minor"] for s in r.json()["splits"]] == [1000, 2000]


# ---- vector 42 ---------------------------------------------------------------------------------------------------

def _deleted_at(db, expense_id):
    t = expenses_table()
    db.expire_all()
    return db.execute(select(t.c.deleted_at).where(t.c.id == uuid.UUID(expense_id))).scalar_one()


def _friend_ids(client, who):
    r = client.get("/friends", headers=h(who))
    assert r.status_code == 200, r.text
    return {f["user"]["id"] for f in r.json()["items"]}  # FriendList = {"items": [...]}


def _nonzero_lines(friend_body):
    return [x for x in friend_body["balances"] if x["amount_minor"] != 0]  # [] until S4; stays correct after S4


def test_vector_42_remove_friend_with_balance_is_204_and_soft_deletes_the_expense(client, db_session):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    assert client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a)).status_code == 201
    assert client.post("/friends", json={"email": "meera@example.com"}, headers=h(a)).status_code == 201
    e = create_expense(client, a, {**equal_body(a, [a, b], total=6000), "group_id": None})  # B owes A 3000
    other = create_expense(client, a, {**equal_body(a, [a, c], total=4000), "group_id": None})  # untouched: with C
    assert _deleted_at(db_session, e["id"]) is None

    r = client.delete(f"/friends/{uid(b)}", headers=h(a))
    assert r.status_code == 204, r.text  # never blocked by a non-zero non-group balance (OQ-32)

    assert _deleted_at(db_session, e["id"]) is not None
    assert _deleted_at(db_session, other["id"]) is None
    assert uid(b) not in _friend_ids(client, a)
    assert uid(a) not in _friend_ids(client, b)
    # the pair has no balance any more (balances are [] until S4; after S4 the friend row is gone, so 404)
    assert client.get(f"/friends/{uid(b)}", headers=h(a)).status_code == 404
    listing = client.get("/expenses", params={"non_group": "true"}, headers=h(a))
    assert listing.status_code == 200
    assert [x["id"] for x in listing.json()["items"]] == [other["id"]]
    # C's view of the other expense is intact
    assert client.get(f"/expenses/{other['id']}", headers=h(c)).status_code == 200


def test_vector_42_removal_leaves_group_expenses_alone(client, db_session):
    """S3-B-4: soft-deletes the pair's NON-group expenses only. The pair first shared a group (balanced there), then B
    left it, which makes them explicit friends (10.1a) with no shared group."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    g1 = create_group_expense(client, a, gid, equal_body(a, [a, b], total=6000))
    g2 = create_group_expense(client, b, gid, equal_body(b, [a, b], total=6000))  # cancels g1: balance 0 in G
    assert client.delete(f"/groups/{gid}/members/me", headers=h(b)).status_code == 204
    n = create_expense(client, a, {**equal_body(a, [a, b], total=6000), "group_id": None})  # B owes A 3000, non-group

    assert client.delete(f"/friends/{uid(b)}", headers=h(a)).status_code == 204
    assert _deleted_at(db_session, n["id"]) is not None
    assert _deleted_at(db_session, g1["id"]) is None and _deleted_at(db_session, g2["id"]) is None
