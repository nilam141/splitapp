"""refresh_tokens.revoked_reason

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("revoked_reason", sa.Text, nullable=True))
    # Before 0002 a revoked row could be rotation, logout or reuse; treat all as rotated (keeps reuse detection on).
    op.execute("UPDATE refresh_tokens SET revoked_reason = 'rotated' WHERE revoked_at IS NOT NULL")
    op.create_check_constraint(
        "ck_refresh_tokens_revoked_reason_valid", "refresh_tokens",
        "revoked_reason IN ('rotated', 'logout', 'reuse_detected', 'password_reset')",
    )
    op.create_check_constraint(
        "ck_refresh_tokens_reason_iff_revoked", "refresh_tokens",
        "(revoked_at IS NULL) = (revoked_reason IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_refresh_tokens_reason_iff_revoked", "refresh_tokens", type_="check")
    op.drop_constraint("ck_refresh_tokens_revoked_reason_valid", "refresh_tokens", type_="check")
    op.drop_column("refresh_tokens", "revoked_reason")
