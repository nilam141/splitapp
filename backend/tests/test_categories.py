"""S2-B-1: GET /categories."""


def test_categories_tree(client):
    r = client.get("/categories")
    assert r.status_code == 200
    assert "max-age=86400" in r.headers["cache-control"]
    parents = r.json()
    assert len(parents) == 7
    assert [p["name"] for p in parents] == [
        "Entertainment", "Food & drink", "Home", "Life", "Transport", "Utilities", "General"]
    for p in parents:
        assert p["parent_id"] is None
        assert len(p["children"]) >= 2
        for c in p["children"]:
            assert c["parent_id"] == p["id"]
            assert c["children"] == []
            assert set(c) == {"id", "parent_id", "slug", "name", "icon", "children"}
    total_children = sum(len(p["children"]) for p in parents)
    assert 35 <= total_children <= 45


def test_category_id_1_is_general_uncategorized(client):
    parents = client.get("/categories").json()
    general = next(p for p in parents if p["name"] == "General")
    child = next(c for c in general["children"] if c["id"] == 1)
    assert child["name"] == "Uncategorized"
    assert child["slug"] == "general.uncategorized"
    assert all(p["id"] != 1 for p in parents)


def test_category_slugs_unique(client):
    parents = client.get("/categories").json()
    slugs = [p["slug"] for p in parents] + [c["slug"] for p in parents for c in p["children"]]
    assert len(slugs) == len(set(slugs))
