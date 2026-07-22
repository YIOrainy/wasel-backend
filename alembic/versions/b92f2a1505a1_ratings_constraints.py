"""ratings constraints

Revision ID: b92f2a1505a1
Revises: 5c276507af0f
Create Date: 2026-07-22 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b92f2a1505a1'
down_revision: str | None = '5c276507af0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        'fk_ratings_shipment_id_shipments', 'ratings', 'shipments',
        ['shipment_id'], ['shipment_id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_ratings_sender_id_users', 'ratings', 'users',
        ['sender_id'], ['user_id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_ratings_capitan_id_users', 'ratings', 'users',
        ['capitan_id'], ['user_id'], ondelete='CASCADE',
    )
    op.create_unique_constraint('uq_ratings_shipment', 'ratings', ['shipment_id'])
    op.create_check_constraint('ck_ratings_stars_range', 'ratings', 'stars BETWEEN 1 AND 5')


def downgrade() -> None:
    op.drop_constraint('ck_ratings_stars_range', 'ratings', type_='check')
    op.drop_constraint('uq_ratings_shipment', 'ratings', type_='unique')
    op.drop_constraint('fk_ratings_capitan_id_users', 'ratings', type_='foreignkey')
    op.drop_constraint('fk_ratings_sender_id_users', 'ratings', type_='foreignkey')
    op.drop_constraint('fk_ratings_shipment_id_shipments', 'ratings', type_='foreignkey')
