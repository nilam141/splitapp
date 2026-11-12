"""expenses, expense_payers, expense_splits, comments, deferred sum-check trigger

Revision ID: 0005
Revises: 0004

`expenses.recurring_rule_id` and `comments.settlement_id` are created without their foreign keys: the target
tables (`recurring_rules`, `settlements`) ship in later slices, whose migrations add the FKs.
The constraint trigger `check_expense_sums` is PostgreSQL only (SQLite test databases rely on the service layer).
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_now = sa.func.now()

_FUNCTION = """
CREATE FUNCTION check_expense_sums() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    eid uuid;
    total bigint;
    paid bigint;
    owed bigint;
BEGIN
    IF TG_TABLE_NAME = 'expenses' THEN
        eid := NEW.id;
    ELSIF TG_OP = 'DELETE' THEN
        eid := OLD.expense_id;
    ELSE
        eid := NEW.expense_id;
    END IF;
    SELECT total_amount_minor INTO total FROM expenses WHERE id = eid;
    IF NOT FOUND THEN
        RETURN NULL;  -- the expense itself is gone (cascade delete): nothing to check
    END IF;
    SELECT COALESCE(SUM(paid_amount_minor), 0) INTO paid FROM expense_payers WHERE expense_id = eid;
    SELECT COALESCE(SUM(owed_amount_minor), 0) INTO owed FROM expense_splits WHERE expense_id = eid;
    IF paid <> total THEN
        RAISE EXCEPTION 'expense % payers sum % <> total %', eid, paid, total USING ERRCODE = '23514';
    END IF;
    IF owed <> total THEN
        RAISE EXCEPTION 'expense % splits sum % <> total %', eid, owed, total USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
"""


def _ts(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=_now if default else None)


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("total_amount_minor", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.CHAR(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("category_id", sa.SmallInteger, sa.ForeignKey("categories.id"), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("expense_date", sa.Date, nullable=False),
        sa.Column("split_type", sa.Text, nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("recurring_rule_id", sa.Uuid, nullable=True),
        sa.Column("occurrence_date", sa.Date, nullable=True),
        sa.Column("fx_original_amount_minor", sa.BigInteger, nullable=True),
        sa.Column("fx_original_currency", sa.CHAR(3), sa.ForeignKey("currencies.code"), nullable=True),
        sa.Column("fx_rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("idempotency_key", sa.Uuid, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        _ts("deleted_at", nullable=True, default=False),
        sa.Column("deleted_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("total_amount_minor > 0 AND total_amount_minor <= 9999999999",
                           name="ck_expenses_total_range"),
        sa.CheckConstraint("split_type IN ('equal', 'exact', 'percent', 'shares', 'adjustment', 'itemized')",
                           name="ck_expenses_split_type"),
        sa.CheckConstraint("char_length(description) BETWEEN 1 AND 200", name="ck_expenses_description_length"),
        sa.CheckConstraint("notes IS NULL OR char_length(notes) <= 2000", name="ck_expenses_notes_length"),
        sa.UniqueConstraint("created_by", "idempotency_key", name="uq_expenses_created_by_idempotency_key"),
        sa.UniqueConstraint("recurring_rule_id", "occurrence_date", name="uq_expenses_rule_occurrence"),
    )
    op.create_index("ix_expenses_group_date_live", "expenses",
                    ["group_id", sa.text("expense_date DESC"), sa.text("created_at DESC"), sa.text("id DESC")],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    op.create_table(
        "expense_payers",
        sa.Column("expense_id", sa.Uuid, sa.ForeignKey("expenses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("paid_amount_minor", sa.BigInteger, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("paid_amount_minor > 0", name="ck_expense_payers_positive"),
    )
    op.create_index("ix_expense_payers_user_id", "expense_payers", ["user_id"])

    op.create_table(
        "expense_splits",
        sa.Column("expense_id", sa.Uuid, sa.ForeignKey("expenses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("owed_amount_minor", sa.BigInteger, nullable=False),
        sa.Column("input_value", sa.BigInteger, nullable=True),
        sa.Column("sort_index", sa.SmallInteger, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("owed_amount_minor >= 0", name="ck_expense_splits_non_negative"),
    )
    op.create_index("ix_expense_splits_user_id", "expense_splits", ["user_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("expense_id", sa.Uuid, sa.ForeignKey("expenses.id"), nullable=True),
        sa.Column("settlement_id", sa.Uuid, nullable=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        _ts("deleted_at", nullable=True, default=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("kind IN ('user', 'system')", name="ck_comments_kind"),
        sa.CheckConstraint("(expense_id IS NOT NULL) <> (settlement_id IS NOT NULL)", name="ck_comments_one_target"),
        sa.CheckConstraint("(kind = 'system') = (user_id IS NULL)", name="ck_comments_system_has_no_user"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 1000", name="ck_comments_body_length"),
    )
    op.create_index("ix_comments_expense_created", "comments", ["expense_id", "created_at", "id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_FUNCTION)
        for table in ("expenses", "expense_payers", "expense_splits"):
            events = "INSERT OR UPDATE OR DELETE" if table != "expenses" else "INSERT OR UPDATE OF total_amount_minor"
            op.execute(
                f"CREATE CONSTRAINT TRIGGER check_expense_sums_{table} AFTER {events} ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_expense_sums()")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("expenses", "expense_payers", "expense_splits"):
            op.execute(f"DROP TRIGGER IF EXISTS check_expense_sums_{table} ON {table}")
        op.execute("DROP FUNCTION IF EXISTS check_expense_sums()")
    for table in ("comments", "expense_splits", "expense_payers", "expenses"):
        op.drop_table(table)
