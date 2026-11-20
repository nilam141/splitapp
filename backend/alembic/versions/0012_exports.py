"""exports

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("requested_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("friend_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("format", sa.Text, nullable=False, server_default="csv"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("storage_key", sa.Text, nullable=True),
        sa.Column("file_name", sa.Text, nullable=True),
        sa.Column("purge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope IN ('group', 'friend')", name="ck_exports_scope"),
        sa.CheckConstraint("format IN ('csv')", name="ck_exports_format"),
        sa.CheckConstraint("status IN ('pending', 'ready', 'failed')", name="ck_exports_status"),
    )
    op.create_index("ix_exports_requested_by", "exports", ["requested_by"])
    op.create_index("ix_exports_purge_at", "exports", ["purge_at"])


def downgrade() -> None:
    op.drop_table("exports")
