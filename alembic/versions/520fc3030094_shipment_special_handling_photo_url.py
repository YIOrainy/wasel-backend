"""shipment special_handling + photo_url

Revision ID: 520fc3030094
Revises: 5c45431e5f9e
Create Date: 2026-06-16 14:56:49.349360

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '520fc3030094'
down_revision: str | None = '5c45431e5f9e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shipments', sa.Column('special_handling', sa.String(), nullable=True))
    op.add_column('shipments', sa.Column('photo_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('shipments', 'photo_url')
    op.drop_column('shipments', 'special_handling')
