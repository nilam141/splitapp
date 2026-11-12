"""currencies, users, refresh_tokens

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.seed import CURRENCIES

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    currencies = op.create_table(
        "currencies",
        sa.Column("code", sa.CHAR(3), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("exponent", sa.SmallInteger, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.CheckConstraint("exponent IN (0, 2, 3)", name="ck_currencies_exponent"),
    )
    op.bulk_insert(
        currencies,
        [{"code": c, "name": n, "symbol": s, "exponent": e, "is_active": True} for c, n, s, e in CURRENCIES],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", postgresql.CITEXT, nullable=True),
        sa.Column("phone_e164", sa.String(16), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=True),
        sa.Column("is_registered", sa.Boolean, nullable=False),
        sa.Column("default_currency", sa.CHAR(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("time_zone", sa.Text, nullable=False, server_default="Asia/Kolkata"),
        sa.Column("locale", sa.String(10), nullable=False, server_default="en-IN"),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("notification_prefs", postgresql.JSONB, nullable=False),
        sa.Column("activity_last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("friend_code", sa.String(16), nullable=False),
        sa.Column("google_sub", sa.Text, nullable=True),
        sa.Column("invited_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("merged_into", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_users_name_length"),
    )
    op.create_index("uq_users_email", "users", ["email"], unique=True, postgresql_where=sa.text("email IS NOT NULL"))
    op.create_index("uq_users_phone_e164", "users", ["phone_e164"], unique=True,
                    postgresql_where=sa.text("phone_e164 IS NOT NULL"))
    op.create_index("uq_users_google_sub", "users", ["google_sub"], unique=True,
                    postgresql_where=sa.text("google_sub IS NOT NULL"))
    op.create_index("uq_users_friend_code", "users", ["friend_code"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        sa.Column("device_label", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("uq_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("currencies")
    op.execute("DROP EXTENSION IF EXISTS citext")
