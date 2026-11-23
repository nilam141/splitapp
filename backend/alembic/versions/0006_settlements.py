"""settlements, the timeline index, and the foreign key from comments.settlement_id

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=sa.func.now() if default else None)


def upgrade() -> None:
    op.create_table(
        "settlements",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("group_id", sa.Uuid, sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("from_user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_minor", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.CHAR(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("settled_on", sa.Date, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("method", sa.Text, nullable=False, server_default="cash"),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("batch_id", sa.Uuid, nullable=True),
        sa.Column("idempotency_key", sa.Uuid, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        _ts("deleted_at", nullable=True, default=False),
        sa.Column("deleted_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("amount_minor > 0 AND amount_minor <= 9999999999", name="ck_settlements_amount_range"),
        sa.CheckConstraint("from_user_id <> to_user_id", name="ck_settlements_distinct_parties"),
        sa.CheckConstraint("method IN ('cash')", name="ck_settlements_method"),
        sa.CheckConstraint("note IS NULL OR char_length(note) <= 500", name="ck_settlements_note_length"),
        sa.UniqueConstraint("created_by", "idempotency_key", name="uq_settlements_created_by_idempotency_key"),
    )
    op.create_index("ix_settlements_group_date_live", "settlements",
                    ["group_id", sa.text("settled_on DESC"), sa.text("created_at DESC"), sa.text("id DESC")],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_settlements_group_id", "settlements", ["group_id"])
    op.create_index("ix_settlements_from_user_id", "settlements", ["from_user_id"])
    op.create_index("ix_settlements_to_user_id", "settlements", ["to_user_id"])
    op.create_foreign_key("fk_comments_settlement_id", "comments", "settlements", ["settlement_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_comments_settlement_id", "comments", type_="foreignkey")
    op.drop_table("settlements")  # drops its indexes with it
