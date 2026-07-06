"""shipment pickup/delivery otp

Revision ID: 5c276507af0f
Revises: 9df6dcd252d9
Create Date: 2026-06-21 11:47:09.666427

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c276507af0f'
down_revision: str | None = '9df6dcd252d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shipments', sa.Column('pickup_otp', sa.String(), nullable=True))
    op.add_column('shipments', sa.Column('delivery_otp', sa.String(), nullable=True))
    # receiver_otp superseded by the pickup/delivery pair above.
    op.drop_column('shipments', 'receiver_otp')


def downgrade() -> None:
    op.add_column('shipments', sa.Column('receiver_otp', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_column('shipments', 'delivery_otp')
    op.drop_column('shipments', 'pickup_otp')
