"""Migration 0004 (activity_log, activity_recipients, rate_limit_events). Needs TEST_DATABASE_URL."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from tests.conftest import PG_URL, alembic_config

pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (PostgreSQL required)")


def test_0004_applies_and_rolls_back():
    eng = create_engine(PG_URL)
    with eng.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "head")
    new = {"activity_log", "activity_recipients", "rate_limit_events"}
    assert new <= set(inspect(eng).get_table_names())
    idx = {i["name"] for i in inspect(eng).get_indexes("activity_recipients")}
    assert "ix_activity_recipients_user_activity" in idx
    command.downgrade(cfg, "0003")
    assert not (new & set(inspect(eng).get_table_names()))
    assert "groups" in inspect(eng).get_table_names()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng.dispose()
