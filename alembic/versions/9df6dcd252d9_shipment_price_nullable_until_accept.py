"""shipment price nullable until accept

Revision ID: 9df6dcd252d9
Revises: 520fc3030094
Create Date: 2026-06-16 15:12:35.901302

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9df6dcd252d9'
down_revision: str | None = '520fc3030094'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "shipments", "price", existing_type=sa.Numeric(10, 2), nullable=True
    )


def downgrade() -> None:
    # NOT NULL again — backfill any NULLs (un-accepted shipments) to 0 first.
    op.execute("UPDATE shipments SET price = 0 WHERE price IS NULL")
    op.alter_column(
        "shipments", "price", existing_type=sa.Numeric(10, 2), nullable=False
    )
