"""S1-Q-2: refresh-token revocation reasons (business_rules 11.1, vectors 46 and 47; gates S1-B-7).

`revoked_reason` is read with raw SQL so these tests do not depend on the ORM model having the attribute
and fail on the missing column / old behaviour until S1-B-7 lands.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import services_auth
from app.errors import ApiError

from tests.test_auth import reg
from tests.test_users_me import _auth

BOB = {"email": "bob@example.com", "name": "Bob"}
LOGIN_A = {"email": "asha@example.com", "password": "abcd1234"}


def _refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


def _logout(client, access, refresh):
    return client.post("/auth/logout", json={"refresh_token": refresh}, headers=_auth(access))


def _rows(engine, email=None):
    """(raw row id -> (revoked_at is not None, revoked_reason)) in creation order is not guaranteed; return list."""
    sql = "select rt.revoked_at, rt.revoked_reason from refresh_tokens rt join users u on u.id = rt.user_id"
    params = {}
    if email:
        sql += " where u.email = :e"
        params["e"] = email
    with engine.connect() as c:
        return [(r[0], r[1]) for r in c.execute(text(sql), params)]


def _reasons(engine, email=None):
    return sorted(str(r) for _, r in _rows(engine, email))


def _assert_token_invalid(r):
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


# ---- reasons are recorded ----

def test_rotation_sets_reason_rotated(client, engine):
    d = reg(client).json()
    assert _refresh(client, d["refresh_token"]).status_code == 200
    rows = _rows(engine)
    assert len(rows) == 2
    assert sorted(str(r) for _, r in rows) == ["None", "rotated"]
    assert all((at is None) == (reason is None) for at, reason in rows)


def test_logout_sets_reason_logout(client, engine):
    d = reg(client).json()
    assert _logout(client, d["access_token"], d["refresh_token"]).status_code == 204
    assert _rows(engine)[0][1] == "logout"
    assert _rows(engine)[0][0] is not None


def test_second_logout_does_not_overwrite_reason(client, engine):
    d = reg(client).json()
    _logout(client, d["access_token"], d["refresh_token"])
    _logout(client, d["access_token"], d["refresh_token"])
    assert [r for _, r in _rows(engine)] == ["logout"]


def test_logout_of_one_token_leaves_other_row_with_null_reason(client, engine):
    d = reg(client).json()
    client.post("/auth/login", json=LOGIN_A)
    _logout(client, d["access_token"], d["refresh_token"])
    assert _reasons(engine) == ["None", "logout"]


# ---- vector 46: logout-revoked token is not reuse ----

def test_vector_46_logout_token_replay_is_401_and_revokes_nothing_else(client, engine):
    r1 = reg(client).json()  # device 1
    r2 = client.post("/auth/login", json=LOGIN_A).json()  # device 2
    other = reg(client, **BOB).json()
    assert _logout(client, r1["access_token"], r1["refresh_token"]).status_code == 204

    _assert_token_invalid(_refresh(client, r1["refresh_token"]))

    rows = _rows(engine, "asha@example.com")
    assert sorted(str(r) for _, r in rows) == ["None", "logout"]  # R2 untouched, R1 still 'logout'
    assert sum(at is None for at, _ in rows) == 1
    assert _reasons(engine, "bob@example.com") == ["None"]
    # R2 still refreshes, and so does the other user
    assert _refresh(client, r2["refresh_token"]).status_code == 200
    assert _refresh(client, other["refresh_token"]).status_code == 200


def test_vector_46_logout_token_replayed_many_times_never_revokes_others(client, engine):
    r1 = reg(client).json()
    r2 = client.post("/auth/login", json=LOGIN_A).json()
    _logout(client, r1["access_token"], r1["refresh_token"])
    for _ in range(3):
        _assert_token_invalid(_refresh(client, r1["refresh_token"]))
    assert _refresh(client, r2["refresh_token"]).status_code == 200


def test_vector_46_logout_replay_after_other_device_rotated_keeps_new_token_alive(client, engine):
    r1 = reg(client).json()
    r2 = client.post("/auth/login", json=LOGIN_A).json()
    r2b = _refresh(client, r2["refresh_token"]).json()
    _logout(client, r1["access_token"], r1["refresh_token"])
    _assert_token_invalid(_refresh(client, r1["refresh_token"]))
    assert _refresh(client, r2b["refresh_token"]).status_code == 200


# ---- vector 47: rotated token is reuse ----

def test_vector_47_rotated_token_replay_revokes_all_with_reuse_detected(client, engine):
    r1 = reg(client).json()
    d2 = client.post("/auth/login", json=LOGIN_A).json()  # another live token of A
    other = reg(client, **BOB).json()
    r2 = _refresh(client, r1["refresh_token"]).json()  # R1 -> R2
    assert _reasons(engine, "asha@example.com") == ["None", "None", "rotated"]

    _assert_token_invalid(_refresh(client, r1["refresh_token"]))

    rows = _rows(engine, "asha@example.com")
    assert len(rows) == 3
    assert all(at is not None for at, _ in rows)
    assert sorted(r for _, r in rows) == ["reuse_detected", "reuse_detected", "rotated"]  # R1 keeps 'rotated'
    for tok in (r2["refresh_token"], d2["refresh_token"]):
        _assert_token_invalid(_refresh(client, tok))
    # another user untouched
    assert _reasons(engine, "bob@example.com") == ["None"]
    assert _refresh(client, other["refresh_token"]).status_code == 200


def test_vector_47_reuse_replay_again_does_not_change_reasons(client, engine):
    r1 = reg(client).json()
    _refresh(client, r1["refresh_token"])
    _assert_token_invalid(_refresh(client, r1["refresh_token"]))
    before = _reasons(engine)
    _assert_token_invalid(_refresh(client, r1["refresh_token"]))
    assert _reasons(engine) == before == ["reuse_detected", "rotated"]


def test_vector_47_presenting_reuse_detected_token_is_401_and_revokes_nothing_new(client, engine):
    r1 = reg(client).json()
    r2 = _refresh(client, r1["refresh_token"]).json()
    _assert_token_invalid(_refresh(client, r1["refresh_token"]))  # r2 now reuse_detected
    # a fresh login after the incident must survive a stale retry of the reuse_detected token r2
    fresh = client.post("/auth/login", json=LOGIN_A).json()
    _assert_token_invalid(_refresh(client, r2["refresh_token"]))
    assert _refresh(client, fresh["refresh_token"]).status_code == 200


def test_vector_47_lost_rotation_race_revokes_all_with_reuse_detected(client, engine):
    data = reg(client).json()
    raw = data["refresh_token"]
    client.post("/auth/login", json=LOGIN_A)  # second live token of A
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as a, factory() as b:
        orig_get = a.get

        def racing_get(*args, **kwargs):
            result = orig_get(*args, **kwargs)
            services_auth.refresh(b, raw)  # B wins the rotation
            return result

        a.get = racing_get
        with pytest.raises(ApiError) as e:
            services_auth.refresh(a, raw)
        assert e.value.status == 401 and e.value.code == "TOKEN_INVALID"
    rows = _rows(engine)
    assert len(rows) == 3  # original, login, B's rotation
    assert all(at is not None for at, _ in rows)
    assert sorted(r for _, r in rows) == ["reuse_detected", "reuse_detected", "rotated"]
