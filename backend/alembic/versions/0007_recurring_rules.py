"""recurring_rules and the foreign key from expenses.recurring_rule_id

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("template_expense_id", sa.Uuid, sa.ForeignKey("expenses.id"), nullable=False),
        sa.Column("interval", sa.Text, nullable=False),
        sa.Column("anchor_date", sa.Date, nullable=False),
        sa.Column("next_occurrence_date", sa.Date, nullable=False),
        sa.Column("reminder_days_before", sa.SmallInteger, nullable=True),
        sa.Column("last_reminded_for", sa.Date, nullable=True),
        sa.Column("time_zone", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("interval IN ('weekly', 'fortnightly', 'monthly', 'yearly')",
                           name="ck_recurring_rules_interval"),
        sa.CheckConstraint("reminder_days_before IS NULL OR (reminder_days_before BETWEEN 0 AND 7)",
                           name="ck_recurring_rules_reminder_days"),
    )
    op.create_index("ix_recurring_rules_next_active", "recurring_rules", ["next_occurrence_date"],
                    postgresql_where=sa.text("active"))
    op.create_index("uq_recurring_rules_template", "recurring_rules", ["template_expense_id"], unique=True)
    op.create_foreign_key("fk_expenses_recurring_rule_id", "expenses", "recurring_rules", ["recurring_rule_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_expenses_recurring_rule_id", "expenses", type_="foreignkey")
    op.drop_table("recurring_rules")
