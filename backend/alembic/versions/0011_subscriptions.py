"""subscriptions

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("plan", sa.Text, nullable=False, server_default="free"),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("store", sa.Text, nullable=True),
        sa.Column("purchase_token_hash", sa.LargeBinary, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("plan IN ('free', 'premium_monthly', 'premium_yearly')", name="ck_subscriptions_plan"),
        sa.CheckConstraint("status IN ('active', 'grace', 'expired', 'cancelled')", name="ck_subscriptions_status"),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
