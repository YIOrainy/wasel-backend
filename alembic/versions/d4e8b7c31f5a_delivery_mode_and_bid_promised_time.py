"""delivery mode replaces client-scheduled times; bids carry a promised delivery time

Revision ID: d4e8b7c31f5a
Revises: b92f2a1505a1
Create Date: 2026-08-18 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8b7c31f5a'
down_revision: str | None = 'b92f2a1505a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # shipments: the client no longer schedules pickup/delivery — it picks a
    # delivery mode instead (pre-launch destructive drop, data not preserved).
    op.drop_column("shipments", "expected_pickup_time")
    op.drop_column("shipments", "expected_delivery_time")
    op.drop_column("shipments", "pickup_asap")
    op.add_column(
        "shipments",
        sa.Column(
            "delivery_mode",
            sa.Enum(
                "fast",
                "regular",
                name="deliverymode",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="regular",
            nullable=False,
        ),
    )
    # NULL until a bid is accepted; snapshot of the winning bid's promise.
    op.add_column(
        "shipments",
        sa.Column("promised_delivery_time", sa.DateTime(timezone=True), nullable=True),
    )

    # bids: every offer now includes the captain's promised delivery moment.
    # Backfill any existing rows (dev data) before tightening to NOT NULL.
    op.add_column(
        "bids",
        sa.Column("promised_delivery_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE bids SET promised_delivery_time = created_at "
        "WHERE promised_delivery_time IS NULL"
    )
    op.alter_column(
        "bids",
        "promised_delivery_time",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("bids", "promised_delivery_time")
    op.drop_column("shipments", "promised_delivery_time")
    op.drop_column("shipments", "delivery_mode")
    # Restore the old NOT NULL columns; original values are gone (destructive
    # upgrade), so backfill with created_at placeholders.
    op.add_column(
        "shipments",
        sa.Column(
            "pickup_asap",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "shipments",
        sa.Column("expected_pickup_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shipments",
        sa.Column("expected_delivery_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE shipments SET expected_pickup_time = created_at, "
        "expected_delivery_time = created_at"
    )
    op.alter_column(
        "shipments",
        "expected_pickup_time",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "shipments",
        "expected_delivery_time",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
