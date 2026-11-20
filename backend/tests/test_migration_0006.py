"""S5-B-1: migration 0006 (settlements, timeline index, comments.settlement_id FK). Round trip needs PostgreSQL."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.db import Base
from tests.conftest import PG_URL, alembic_config

needs_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (PostgreSQL required)")


def test_model_declares_settlements():
    t = Base.metadata.tables["settlements"]
    assert {"group_id", "from_user_id", "to_user_id", "amount_minor", "currency", "settled_on", "note", "method",
            "created_by", "batch_id", "idempotency_key", "version", "deleted_at", "deleted_by"} <= set(t.c.keys())
    assert {i.name for i in t.indexes} >= {"ix_settlements_group_date_live", "ix_settlements_group_id",
                                           "ix_settlements_from_user_id", "ix_settlements_to_user_id"}


@needs_pg
def test_0006_applies_and_rolls_back():
    eng = create_engine(PG_URL)
    with eng.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "head")
    insp = inspect(eng)
    assert "settlements" in insp.get_table_names()
    assert {"ix_settlements_group_date_live", "ix_settlements_from_user_id", "ix_settlements_to_user_id",
            "ix_settlements_group_id"} <= {i["name"] for i in insp.get_indexes("settlements")}
    assert any(fk["referred_table"] == "settlements" for fk in insp.get_foreign_keys("comments"))
    command.downgrade(cfg, "0005")
    insp = inspect(eng)
    assert "settlements" not in insp.get_table_names() and "comments" in insp.get_table_names()
    assert not any(fk["referred_table"] == "settlements" for fk in insp.get_foreign_keys("comments"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng.dispose()
