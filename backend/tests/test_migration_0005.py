"""S3-B-2: migration 0005 (expenses, expense_payers, expense_splits, comments, deferred sum-check trigger).

The trigger and the round trip need PostgreSQL (TEST_DATABASE_URL). The model-level checks also run on SQLite.
"""
import uuid
from datetime import date

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import Base
from tests.conftest import PG_URL, alembic_config
from tests.test_auth import reg

needs_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (PostgreSQL required)")


def test_models_declare_the_new_tables_and_columns():
    t = Base.metadata.tables
    assert {"expenses", "expense_payers", "expense_splits", "comments"} <= set(t)
    cols = set(t["expenses"].c.keys())
    assert {"recurring_rule_id", "occurrence_date", "idempotency_key", "fx_original_amount_minor",
            "fx_original_currency", "fx_rate", "version", "deleted_at", "deleted_by"} <= cols
    assert not t["expenses"].c.recurring_rule_id.foreign_keys  # FK arrives with recurring_rules (S6-B-1)
    assert not t["comments"].c.settlement_id.foreign_keys      # FK arrives with settlements (S5-B-1)


@needs_pg
def test_0005_applies_and_rolls_back():
    eng = create_engine(PG_URL)
    with eng.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")
    cfg = alembic_config(PG_URL)
    command.upgrade(cfg, "head")
    new = {"expenses", "expense_payers", "expense_splits", "comments"}
    assert new <= set(inspect(eng).get_table_names())
    idx = {i["name"] for i in inspect(eng).get_indexes("expenses")}
    assert "ix_expenses_group_date_live" in idx
    assert "ix_expense_splits_user_id" in {i["name"] for i in inspect(eng).get_indexes("expense_splits")}
    assert "ix_expense_payers_user_id" in {i["name"] for i in inspect(eng).get_indexes("expense_payers")}
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'check_expense_sums_%'")).scalar() == 3
    command.downgrade(cfg, "0004")
    assert not (new & set(inspect(eng).get_table_names()))
    assert "groups" in inspect(eng).get_table_names()
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'check_expense_sums'")).scalar() == 0
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng.dispose()


# ---- the deferred trigger: direct SQL, no service layer ----------------------------------------------------------

@pytest.fixture()
def uid(client):
    return uuid.UUID(reg(client).json()["user"]["id"])


def _expense(conn, uid, total=10000, eid=None):
    eid = eid or uuid.uuid4()
    conn.execute(text(
        "INSERT INTO expenses (id, description, total_amount_minor, currency, expense_date, split_type, created_by)"
        " VALUES (:id, 'x', :t, 'INR', :d, 'equal', :u)"), {"id": eid, "t": total, "d": date(2026, 11, 5), "u": uid})
    return eid


def _payer(conn, eid, uid, amount):
    conn.execute(text("INSERT INTO expense_payers (expense_id, user_id, paid_amount_minor) VALUES (:e, :u, :a)"),
                 {"e": eid, "u": uid, "a": amount})


def _split(conn, eid, uid, amount):
    conn.execute(text("INSERT INTO expense_splits (expense_id, user_id, owed_amount_minor, sort_index)"
                      " VALUES (:e, :u, :a, 0)"), {"e": eid, "u": uid, "a": amount})


def _commit_fails(engine, work):
    """Run `work(conn)`; every statement must succeed, the failure must come only when the transaction commits."""
    conn = engine.connect()
    try:
        work(conn)
        with pytest.raises(IntegrityError):
            conn.commit()
    finally:
        conn.close()


@needs_pg
def test_consistent_expense_commits(engine, uid):
    with engine.begin() as c:
        e = _expense(c, uid)
        _payer(c, e, uid, 10000)
        _split(c, e, uid, 10000)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM expenses")).scalar() == 1


@needs_pg
def test_splits_not_summing_to_total_fail_at_commit(engine, uid):
    def work(c):
        e = _expense(c, uid)
        _payer(c, e, uid, 10000)
        _split(c, e, uid, 9999)  # the INSERT is accepted; the deferred trigger rejects it at commit
    _commit_fails(engine, work)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM expenses")).scalar() == 0


@needs_pg
def test_payers_not_summing_to_total_fail_at_commit(engine, uid):
    def work(c):
        e = _expense(c, uid)
        _payer(c, e, uid, 5000)
        _split(c, e, uid, 10000)
    _commit_fails(engine, work)


@needs_pg
def test_expense_without_payers_or_splits_fails_at_commit(engine, uid):
    _commit_fails(engine, lambda c: _expense(c, uid))


@needs_pg
def test_changing_the_total_alone_fails_but_with_the_rows_in_the_same_transaction_passes(engine, uid):
    with engine.begin() as c:
        e = _expense(c, uid)
        _payer(c, e, uid, 10000)
        _split(c, e, uid, 10000)
    _commit_fails(engine, lambda c: c.execute(text("UPDATE expenses SET total_amount_minor = 12000 WHERE id = :e"),
                                              {"e": e}))
    with engine.begin() as c:
        c.execute(text("UPDATE expenses SET total_amount_minor = 12000 WHERE id = :e"), {"e": e})
        c.execute(text("UPDATE expense_payers SET paid_amount_minor = 12000 WHERE expense_id = :e"), {"e": e})
        c.execute(text("UPDATE expense_splits SET owed_amount_minor = 12000 WHERE expense_id = :e"), {"e": e})


@needs_pg
def test_deleting_a_payer_row_fails_but_soft_delete_and_cascade_do_not(engine, uid):
    with engine.begin() as c:
        e = _expense(c, uid)
        _payer(c, e, uid, 10000)
        _split(c, e, uid, 10000)
    _commit_fails(engine, lambda c: c.execute(text("DELETE FROM expense_payers WHERE expense_id = :e"), {"e": e}))
    with engine.begin() as c:
        c.execute(text("UPDATE expenses SET deleted_at = now() WHERE id = :e"), {"e": e})
    with engine.begin() as c:  # removing the whole expense (rows cascade) is fine
        c.execute(text("DELETE FROM expenses WHERE id = :e"), {"e": e})


@needs_pg
def test_table_checks_and_unique_keys(engine, uid):
    for total in (0, 10_000_000_000):
        with engine.connect() as c, pytest.raises(IntegrityError):
            _expense(c, uid, total=total)
    with engine.connect() as c, pytest.raises(IntegrityError):
        c.execute(text("INSERT INTO comments (id, kind, body) VALUES (:i, 'user', 'hi')"), {"i": uuid.uuid4()})
    key = uuid.uuid4()
    with engine.connect() as c:
        for _ in range(2):
            e = uuid.uuid4()
            try:
                c.execute(text(
                    "INSERT INTO expenses (id, description, total_amount_minor, currency, expense_date, split_type,"
                    " created_by, idempotency_key) VALUES (:id, 'x', 1, 'INR', :d, 'equal', :u, :k)"),
                    {"id": e, "d": date(2026, 11, 5), "u": uid, "k": key})
            except IntegrityError:
                break
        else:
            pytest.fail("(created_by, idempotency_key) must be unique")
