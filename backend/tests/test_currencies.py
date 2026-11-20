def test_currencies_list(client):
    r = client.get("/currencies")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 30
    by_code = {c["code"]: c for c in items}
    assert by_code["INR"]["exponent"] == 2
    assert by_code["JPY"]["exponent"] == 0
    assert by_code["KWD"]["exponent"] == 3
    assert set(items[0]) == {"code", "name", "symbol", "exponent"}
    assert all(isinstance(c["exponent"], int) for c in items)
    assert len({c["code"] for c in items}) == len(items)


def test_currencies_needs_no_auth_and_is_cacheable(client):
    r = client.get("/currencies")
    assert "max-age=86400" in r.headers["cache-control"]
