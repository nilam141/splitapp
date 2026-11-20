"""receipts

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("expense_id", sa.Uuid, sa.ForeignKey("expenses.id"), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("uploaded_by", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ocr_payload", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("content_type IN ('image/jpeg', 'image/png')", name="ck_receipts_content_type"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_receipts_size"),
    )
    op.create_index("uq_receipts_expense", "receipts", ["expense_id"], unique=True)


def downgrade() -> None:
    op.drop_table("receipts")
