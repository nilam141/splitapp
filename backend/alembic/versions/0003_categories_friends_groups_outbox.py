"""categories, friendships, groups, group_members, password_reset_tokens, notifications, idempotency_keys

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.seed import category_rows

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_now = sa.func.now()


def _ts(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=_now if default else None)


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
        sa.Column("parent_id", sa.SmallInteger, sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("icon", sa.Text, nullable=False),
        sa.Column("sort_index", sa.SmallInteger, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    rows = category_rows()
    op.bulk_insert(categories, [r for r in rows if r["parent_id"] is None])  # parents first (self FK)
    op.bulk_insert(categories, [r for r in rows if r["parent_id"] is not None])

    op.create_table(
        "friendships",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("friend_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("blocked_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("removed_at", nullable=True, default=False),
        sa.CheckConstraint("user_id < friend_id", name="ck_friendships_ordered"),
        sa.CheckConstraint("status IN ('active', 'removed', 'blocked')", name="ck_friendships_status"),
    )
    op.create_index("ix_friendships_friend_id", "friendships", ["friend_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("group_type", sa.Text, nullable=False),
        sa.Column("simplify_debts", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("default_currency", sa.CHAR(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("trip_start_date", sa.Date, nullable=True),
        sa.Column("trip_end_date", sa.Date, nullable=True),
        sa.Column("whiteboard", sa.Text, nullable=True),
        sa.Column("whiteboard_updated_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        _ts("deleted_at", nullable=True, default=False),
        sa.Column("deleted_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_groups_name_length"),
        sa.CheckConstraint("group_type IN ('home', 'trip', 'couple', 'other')", name="ck_groups_type"),
        sa.CheckConstraint(
            "trip_end_date IS NULL OR trip_start_date IS NULL OR trip_end_date >= trip_start_date",
            name="ck_groups_trip_dates",
        ),
    )

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.Text, nullable=False, server_default="member"),
        sa.Column("sort_index", sa.Integer, nullable=False),
        _ts("joined_at"),
        _ts("left_at", nullable=True, default=False),
        sa.Column("added_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("role IN ('member', 'admin')", name="ck_group_members_role"),
    )
    # Friend-list derivation (OQ-33): which groups is a user currently in.
    op.create_index(
        "ix_group_members_user_group_active", "group_members", ["user_id", "group_id"],
        postgresql_where=sa.text("left_at IS NULL"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        _ts("expires_at", default=False),
        _ts("used_at", nullable=True, default=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("uq_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("activity_id", sa.Uuid, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        _ts("sent_at", nullable=True, default=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("channel IN ('push', 'email')", name="ck_notifications_channel"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped_pref')", name="ck_notifications_status"),
    )
    op.create_index("ix_notifications_status_created", "notifications", ["status", "created_at"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("key", sa.Uuid, primary_key=True),
        sa.Column("method_path", sa.Text, nullable=False),
        sa.Column("response_status", sa.SmallInteger, nullable=False),
        sa.Column("response_body", postgresql.JSONB, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )


def downgrade() -> None:
    for table in ("idempotency_keys", "notifications", "password_reset_tokens", "group_members", "groups",
                  "friendships", "categories"):
        op.drop_table(table)
