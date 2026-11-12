"""S3-B-5: GET/POST /expenses/{id}/comments."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from app.models import Comment
from tests.expense_helpers import create_expense, create_group_expense, equal_body, h, make_group, uid, user


@pytest.fixture()
def g(client):
    a, b, c, d = (user(client, n) for n in ("Asha", "Ravi", "Meera", "Dev"))
    gid = make_group(client, a, [b, c])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))  # C is a group member but not on the expense
    return {"a": a, "b": b, "c": c, "d": d, "gid": gid, "e": e}


def post(client, who, e, text, **kw):
    return client.post(f"/expenses/{e['id']}/comments", json={"body": text}, headers=h(who), **kw)


def lst(client, who, e, **params):
    return client.get(f"/expenses/{e['id']}/comments", params=params, headers=h(who))


def test_post_and_list_oldest_first(client, g):
    a, b, e = g["a"], g["b"], g["e"]
    r1 = post(client, a, e, "first")
    assert r1.status_code == 201
    c1 = r1.json()
    assert set(c1) == {"id", "kind", "user", "body", "created_at"} and c1["kind"] == "user" and c1["body"] == "first"
    assert c1["user"] == {"id": uid(a), "name": "Asha", "email": "asha@example.com", "avatar_url": None,
                          "is_registered": True}
    post(client, b, e, "second")
    post(client, a, e, "third")
    page = lst(client, a, e).json()
    assert [c["body"] for c in page["items"]] == ["first", "second", "third"] and page["next_cursor"] is None
    assert page["items"][1]["user"]["id"] == uid(b)
    assert client.get(f"/expenses/{e['id']}", headers=h(a)).json()["comment_count"] == 3


def test_cursor_paging_has_no_gap_and_no_duplicate(client, db_session, g):
    a, e = g["a"], g["e"]
    for i in range(5):
        post(client, a, e, f"c{i}")
    seen, cursor, pages = [], None, 0
    while True:
        page = lst(client, a, e, limit=2, **({"cursor": cursor} if cursor else {})).json()
        seen += [c["body"] for c in page["items"]]
        cursor, pages = page["next_cursor"], pages + 1
        if cursor is None:
            break
    assert seen == [f"c{i}" for i in range(5)] and pages == 3
    # a comment added between pages shows up later, nothing is repeated
    first = lst(client, a, e, limit=2).json()
    post(client, a, e, "late")
    rest = lst(client, a, e, limit=10, cursor=first["next_cursor"]).json()
    assert [c["body"] for c in rest["items"]] == ["c2", "c3", "c4", "late"]


def test_identical_created_at_orders_by_id(client, db_session, g):
    a, e = g["a"], g["e"]
    ids = [post(client, a, e, f"c{i}").json()["id"] for i in range(4)]
    db_session.execute(update(Comment).values(created_at=datetime(2026, 11, 5, 9, tzinfo=timezone.utc)))
    db_session.commit()
    assert [c["id"] for c in lst(client, a, e).json()["items"]] == sorted(ids)
    flat, cursor = [], None
    while True:
        page = lst(client, a, e, limit=1, **({"cursor": cursor} if cursor else {})).json()
        flat += [c["id"] for c in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert flat == sorted(ids)


def test_commenting_on_a_deleted_expense_is_409_and_listing_still_works(client, g):
    a, e = g["a"], g["e"]
    post(client, a, e, "before")
    assert client.delete(f"/expenses/{e['id']}", headers=h(a)).status_code == 200
    r = post(client, a, e, "after")
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_DELETED"
    assert [c["body"] for c in lst(client, a, e).json()["items"]] == ["before"]
    client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    assert post(client, a, e, "after restore").status_code == 201


@pytest.mark.parametrize("payload", [{"body": ""}, {"body": "   "}, {}, {"body": None}, {"body": "x" * 1001},
                                     {"body": 5}])
def test_invalid_body_is_422(client, g, payload):
    r = client.post(f"/expenses/{g['e']['id']}/comments", json=payload, headers=h(g["a"]))
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert lst(client, g["a"], g["e"]).json()["items"] == []


def test_body_limits_and_trimming(client, g):
    assert post(client, g["a"], g["e"], "x" * 1000).status_code == 201
    assert post(client, g["a"], g["e"], "  hi  ").json()["body"] == "hi"


def test_non_participant_is_403_group_member_is_allowed(client, g):
    d, c, e = g["d"], g["c"], g["e"]
    for r in (post(client, d, e, "hi"), lst(client, d, e)):
        assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    assert post(client, c, e, "I am in the group").status_code == 201
    assert lst(client, c, e).status_code == 200
    assert lst(client, d, e).status_code == 403  # nothing leaked by the other member's comment


def test_non_group_expense_comments_need_participation(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    client.post("/friends", json={"email": "ravi@example.com"}, headers=h(a))
    e = create_expense(client, a, equal_body(a, [a, b]))
    assert post(client, b, e, "hi").status_code == 201
    assert post(client, c, e, "hi").status_code == 403 and lst(client, c, e).status_code == 403


def test_unknown_expense_auth_and_cursor_errors(client, g):
    a, e = g["a"], g["e"]
    ghost = {"id": str(uuid.uuid4())}
    assert post(client, a, ghost, "hi").status_code == 404 and lst(client, a, ghost).status_code == 404
    assert client.get(f"/expenses/{e['id']}/comments").status_code == 401
    assert client.post(f"/expenses/{e['id']}/comments", json={"body": "x"}).status_code == 401
    bad = lst(client, a, e, cursor="garbage")
    assert bad.status_code == 422 and bad.json()["details"]["fields"][0]["field"] == "cursor"
    assert lst(client, a, e, limit=0).status_code == 422 and lst(client, a, e, limit=101).status_code == 422
    # a timeline cursor (carries a date) is not a comment cursor
    t = client.get(f"/groups/{g['gid']}/timeline", params={"limit": 1}, headers=h(a))
    create_group_expense(client, a, g["gid"], equal_body(a, [a, g["b"]]))
    tl = client.get(f"/groups/{g['gid']}/timeline", params={"limit": 1}, headers=h(a)).json()["next_cursor"]
    assert t.status_code == 200 and lst(client, a, e, cursor=tl).status_code == 422


def test_system_comments_are_listed_among_user_comments_in_order(client, g):
    a, b, e = g["a"], g["b"], g["e"]
    post(client, a, e, "hello")
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 12000, "currency": "INR"}},
                     headers=h(b))
    assert r.status_code == 200
    post(client, b, e, "ok now")
    items = lst(client, a, e).json()["items"]
    assert [(c["kind"], c["body"]) for c in items] == [("user", "hello"), ("system", "total 100.00 → 120.00"),
                                                      ("user", "ok now")]
    assert items[1]["user"] is None
