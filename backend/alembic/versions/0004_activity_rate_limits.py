"""activity_log, activity_recipients, rate_limit_events

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.Uuid, nullable=False),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    )
    op.create_index("ix_activity_log_created_at", "activity_log", ["created_at"])

    op.create_table(
        "activity_recipients",
        sa.Column("activity_id", sa.Uuid, sa.ForeignKey("activity_log.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("balance_effect", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_activity_recipients_user_activity", "activity_recipients",
                    ["user_id", sa.text("activity_id DESC")])

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("key_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limit_events_scope_key_created", "rate_limit_events",
                    ["scope", "key_hash", "created_at"])


def downgrade() -> None:
    for table in ("rate_limit_events", "activity_recipients", "activity_log"):
        op.drop_table(table)
