"""S5-B-3 backend tests beyond the QA vectors: paging over 120 events, my_effect for expenses and settlements, the
activity written by every expense / settlement / comment action."""
from tests.expense_helpers import create_group_expense, equal_body, h, make_group, uid, user
from tests.settlement_helpers import pay


def feed(client, who, **params):
    r = client.get("/activity", params=params, headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


def effect(item):
    return {(x["currency"]): x["amount_minor"] for x in item["my_effect"]}


def test_120_events_page_as_50_50_20_with_one_unread_count(client):
    """120 entries in A's feed; the 2 by A (group, expense) are never unread for A (S5-B-5), B's 118 comments are."""
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])                                                    # 1 event, by A
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))                     # 1 event, by A
    for i in range(118):
        assert client.post(f"/expenses/{e['id']}/comments", json={"body": f"c{i}"}, headers=h(b)).status_code == 201
    seen, cursor, sizes = [], None, []
    for _ in range(5):
        page = feed(client, a, **({"cursor": cursor} if cursor else {}))
        assert page["unread_count"] == 118
        sizes.append(len(page["items"]))
        seen += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert sizes == [50, 50, 20] and len({i["id"] for i in seen}) == 120
    assert sum(1 for i in seen if i["is_unread"]) == 118


def test_my_effect_for_an_equal_three_way_expense_03a(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c])
    create_group_expense(client, a, gid, equal_body(a, [a, b, c], total=10000))
    top = feed(client, b, group_id=gid)["items"][0]
    assert top["action"] == "expense.created" and effect(top) == {"INR": -3333}
    assert effect(feed(client, c)["items"][0]) == {"INR": -3333}
    top_a = feed(client, a)["items"][0]
    assert effect(top_a) == {"INR": 6666} and top_a["actor"]["id"] == uid(a)
    assert top_a["summary"]["description"] == "Dinner" and top_a["summary"]["total"]["amount_minor"] == 10000


def test_expense_edit_delete_restore_effects(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b], total=10000))
    r = client.patch(f"/expenses/{e['id']}", json={"version": 1, "total": {"amount_minor": 12000, "currency": "INR"}},
                     headers=h(a))
    assert r.status_code == 200
    up = feed(client, b)["items"][0]
    assert up["action"] == "expense.updated" and effect(up) == {"INR": -1000}      # owed 5000 -> 6000
    client.delete(f"/expenses/{e['id']}", headers=h(a))
    de = feed(client, b)["items"][0]
    assert de["action"] == "expense.deleted" and effect(de) == {"INR": 6000}       # the debt is removed
    client.post(f"/expenses/{e['id']}/restore", headers=h(a))
    rs = feed(client, b)["items"][0]
    assert rs["action"] == "expense.restored" and effect(rs) == {"INR": -6000}


def test_settlement_actions_write_activity_with_effects(client):
    a, b, c = user(client, "Asha"), user(client, "Ravi"), user(client, "Meera")
    gid = make_group(client, a, [b, c])
    s = pay(client, c, b, a, 2000, group_id=gid)                     # C records B paying A
    for who, expected in ((b, 2000), (a, -2000)):
        top = feed(client, who)["items"][0]
        assert top["action"] == "settlement.created" and top["entity_type"] == "settlement"
        assert top["entity_id"] == s["id"] and effect(top) == {"INR": expected} and top["group_id"] == gid
    assert effect(feed(client, c)["items"][0]) == {}                  # the actor is neither party: no effect
    client.patch(f"/settlements/{s['id']}", json={"version": 1, "amount": {"amount_minor": 2500, "currency": "INR"}},
                 headers=h(a))
    up = feed(client, b)["items"][0]
    assert up["action"] == "settlement.updated" and effect(up) == {"INR": 500}
    client.delete(f"/settlements/{s['id']}", headers=h(a))
    de = feed(client, b)["items"][0]
    assert de["action"] == "settlement.deleted" and effect(de) == {"INR": -2500}
    client.post(f"/settlements/{s['id']}/restore", headers=h(a))
    assert feed(client, b)["items"][0]["action"] == "settlement.restored"


def test_comment_activity_and_group_filter(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    e = create_group_expense(client, a, gid, equal_body(a, [a, b]))
    client.post(f"/expenses/{e['id']}/comments", json={"body": "hi"}, headers=h(b))
    top = feed(client, a)["items"][0]
    assert top["action"] == "comment.created" and top["entity_type"] == "comment" and top["actor"]["id"] == uid(b)
    assert [i["action"] for i in feed(client, a, group_id=gid)["items"]] == [
        "comment.created", "expense.created", "group.created"]


def test_a_failed_write_leaves_no_activity(client):
    a, b = user(client, "Asha"), user(client, "Ravi")
    gid = make_group(client, a, [b])
    r = client.post("/settlements", json={"group_id": gid, "from_user_id": uid(a), "to_user_id": uid(a),
                                          "amount": {"amount_minor": 5, "currency": "INR"}}, headers=h(a))
    assert r.status_code == 422
    assert [i["action"] for i in feed(client, a)["items"]] == ["group.created"]
