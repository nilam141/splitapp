"""group_invites

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_invites",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("token", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_group_invites_token", "group_invites", ["token"], unique=True)
    op.create_index("uq_group_invites_active_group", "group_invites", ["group_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL"))


def downgrade() -> None:
    op.drop_table("group_invites")
