"""push_devices and reminders

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.Text, nullable=False, server_default="android"),
        sa.Column("token", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("platform IN ('android')", name="ck_push_devices_platform"),
    )
    op.create_index("uq_push_devices_token", "push_devices", ["token"], unique=True)
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("from_user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("message IS NULL OR char_length(message) <= 1000", name="ck_reminders_message_length"),
    )
    op.create_index("ix_reminders_pair_sent", "reminders", ["from_user_id", "to_user_id", "sent_at"])


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("push_devices")
