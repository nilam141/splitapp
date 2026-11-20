"""S6-B-1..S6-B-7: migrations 0007-0012 apply and roll back one step at a time (PostgreSQL only) and the models match."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.db import Base
from tests.conftest import PG_URL, alembic_config

needs_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (PostgreSQL required)")

STEPS = [  # (revision, table it adds, the revision before it)
    ("0007", "recurring_rules", "0006"), ("0008", "reminders", "0007"), ("0009", "group_invites", "0008"),
    ("0010", "receipts", "0009"), ("0011", "subscriptions", "0010"), ("0012", "exports", "0011"),
]


def test_models_declare_the_slice6_tables():
    t = Base.metadata.tables
    assert {"recurring_rules", "push_devices", "reminders", "group_invites", "receipts", "subscriptions",
            "exports"} <= set(t)
    assert {fk.column.table.name for fk in t["expenses"].c.recurring_rule_id.foreign_keys} == {"recurring_rules"}
    assert {"template_expense_id", "interval", "anchor_date", "next_occurrence_date", "reminder_days_before",
            "time_zone", "active", "created_by"} <= set(t["recurring_rules"].c.keys())
    assert {"from_user_id", "to_user_id", "group_id", "message", "sent_at"} <= set(t["reminders"].c.keys())
    assert {"group_id", "token", "created_by", "revoked_at"} <= set(t["group_invites"].c.keys())
    assert {"expense_id", "storage_key", "content_type", "size_bytes", "uploaded_by"} <= set(t["receipts"].c.keys())
    assert {"user_id", "plan", "status", "current_period_end", "store", "purchase_token_hash"} <= set(t["subscriptions"].c.keys())
    assert {"requested_by", "scope", "group_id", "friend_id", "format", "status", "storage_key", "purge_at"} <= set(t["exports"].c.keys())


@needs_pg
def test_each_step_applies_and_rolls_back():
    eng = create_engine(PG_URL)
    with eng.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "0006")
    for rev, table, prev in STEPS:
        command.upgrade(cfg, rev)
        assert table in inspect(eng).get_table_names(), rev
        command.downgrade(cfg, prev)
        assert table not in inspect(eng).get_table_names(), rev
        command.upgrade(cfg, rev)
    insp = inspect(eng)
    assert any(fk["referred_table"] == "recurring_rules" for fk in insp.get_foreign_keys("expenses"))
    assert {"uq_group_invites_active_group", "uq_group_invites_token"} <= {i["name"] for i in insp.get_indexes("group_invites")}
    assert "ix_recurring_rules_next_active" in {i["name"] for i in insp.get_indexes("recurring_rules")}
    command.downgrade(cfg, "0006")
    assert not any(fk["referred_table"] == "recurring_rules" for fk in inspect(eng).get_foreign_keys("expenses"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng.dispose()
