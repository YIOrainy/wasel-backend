from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models._enums import BidStatus
from app.db.models._helpers import enum_values

if TYPE_CHECKING:
    from app.db.models.shipment import Shipment
    from app.db.models.user import User


class Bid(Base):
    __tablename__ = "bids"

    bid_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("shipments.shipment_id", ondelete="CASCADE"),
        nullable=False,
    )
    capitan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[BidStatus] = mapped_column(
        Enum(
            BidStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=enum_values,
            name="bidstatus",
        ),
        nullable=False,
        default=BidStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    shipment: Mapped[Shipment] = relationship(back_populates="bids")
    capitan: Mapped[User] = relationship(back_populates="bids")

    __table_args__ = (
        # one active bid per captain per shipment — re-bidding is an UPDATE
        UniqueConstraint("shipment_id", "capitan_id", name="uq_bids_shipment_capitan"),
        CheckConstraint("price > 0", name="ck_bids_price_positive"),
    )
