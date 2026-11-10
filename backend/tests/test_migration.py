"""Migration apply / rollback. Needs a scratch PostgreSQL database: set TEST_DATABASE_URL."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from tests.conftest import PG_URL, alembic_config

pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (PostgreSQL required)")


def _reset(eng):
    with eng.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")


def test_upgrade_seed_downgrade_upgrade():
    eng = create_engine(PG_URL)
    _reset(eng)
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "head")
    insp = inspect(eng)
    assert {"currencies", "users", "refresh_tokens"} <= set(insp.get_table_names())
    with eng.connect() as c:
        assert c.execute(text("select count(*) from currencies")).scalar() >= 30
        assert c.execute(text("select exponent from currencies where code='INR'")).scalar() == 2
        assert c.execute(text("select exponent from currencies where code='JPY'")).scalar() == 0
    command.downgrade(cfg, "base")
    assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    eng.dispose()


# ---- S1-Q-2 / S1-B-7: migration 0002 (refresh_tokens.revoked_reason) ----

def _seed_0001(eng):
    """One revoked and one live refresh token for one user, at revision 0001."""
    with eng.begin() as c:
        c.execute(text(
            "insert into users (id, email, name, is_registered, default_currency, notification_prefs, friend_code) "
            "values ('00000000-0000-0000-0000-0000000000a1', 'm@example.com', 'M', true, 'INR', '{}'::jsonb, 'FC000001')"
        ))
        for rid, h, revoked in (
            ("00000000-0000-0000-0000-0000000000b1", b"h-revoked", "now()"),
            ("00000000-0000-0000-0000-0000000000b2", b"h-live", "null"),
        ):
            c.execute(
                text(
                    "insert into refresh_tokens (id, user_id, token_hash, expires_at, revoked_at) values "
                    f"('{rid}', '00000000-0000-0000-0000-0000000000a1', :h, now() + interval '30 days', {revoked})"
                ),
                {"h": h},
            )


def test_migration_0002_adds_column_and_backfills_revoked_as_rotated():
    eng = create_engine(PG_URL)
    _reset(eng)
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "0001")
    assert "revoked_reason" not in {c["name"] for c in inspect(eng).get_columns("refresh_tokens")}
    _seed_0001(eng)
    command.upgrade(cfg, "0002")
    insp = inspect(eng)
    cols = {c["name"]: c for c in insp.get_columns("refresh_tokens")}
    assert "revoked_reason" in cols and cols["revoked_reason"]["nullable"] is True
    with eng.connect() as c:
        got = dict(c.execute(text("select token_hash, revoked_reason from refresh_tokens")).all())
    assert got == {b"h-revoked": "rotated", b"h-live": None}
    eng.dispose()


def test_migration_0002_check_constraints():
    from sqlalchemy.exc import IntegrityError

    eng = create_engine(PG_URL)
    _reset(eng)
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "0001")
    _seed_0001(eng)
    command.upgrade(cfg, "0002")
    bad = [
        "update refresh_tokens set revoked_reason = 'bogus' where token_hash = 'h-revoked'::bytea",  # not in list
        "update refresh_tokens set revoked_reason = 'logout' where token_hash = 'h-live'::bytea",  # reason w/o revoked_at
        "update refresh_tokens set revoked_reason = null where token_hash = 'h-revoked'::bytea",  # revoked_at w/o reason
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            with eng.begin() as c:
                c.execute(text(sql))
    for reason in ("rotated", "logout", "reuse_detected", "password_reset"):
        with eng.begin() as c:
            c.execute(text("update refresh_tokens set revoked_reason = :r where token_hash = 'h-revoked'::bytea"), {"r": reason})
    eng.dispose()


def test_migration_0002_downgrade_to_0001_drops_column_and_is_reversible():
    eng = create_engine(PG_URL)
    _reset(eng)
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "head")
    assert "revoked_reason" in {c["name"] for c in inspect(eng).get_columns("refresh_tokens")}
    command.downgrade(cfg, "0001")
    assert "revoked_reason" not in {c["name"] for c in inspect(eng).get_columns("refresh_tokens")}
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert "revoked_reason" in {c["name"] for c in inspect(eng).get_columns("refresh_tokens")}
    eng.dispose()
