from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.capitan_profile import CapitanProfile
    from app.db.models.user import User


class Shipment(Base):
    __tablename__ = "shipments"

    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    capitan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    pickup_city: Mapped[str] = mapped_column(String, nullable=False)
    destination_city: Mapped[str] = mapped_column(String, nullable=False)
    pickup_lat: Mapped[float] = mapped_column(nullable=False)
    pickup_lng: Mapped[float] = mapped_column(nullable=False)
    destination_lat: Mapped[float] = mapped_column(nullable=False)
    destination_lng: Mapped[float] = mapped_column(nullable=False)
    # status: Mapped[str] = mapped_column(String, nullable=False, default="pending") should be enum
    # type = Mapped[str] = mapped_column(String, nullable=False) should be enum
    receiver_phone_number: Mapped[str] = mapped_column(String, nullable=True)
    expected_pickup_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_delivery_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_asap: Mapped[bool] = mapped_column(nullable=False, default=False)
    price: Mapped[float] = mapped_column(nullable=False, default=0.0)
    receiver_otp: Mapped[str] = mapped_column(String, nullable=True)

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

    # Lifecycle milestones
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    picked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    out_for_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sender: Mapped[User] = relationship(
        back_populates="shipments_sent",
        foreign_keys=[sender_id],
    )
    capitan: Mapped[User | None] = relationship(
        back_populates="shipments_assigned",
        foreign_keys=[capitan_id],
    )
    # Convenience: the assigned captain's profile (rating, trips, …), joined on
    # the shared user_id. view-only — capitan_id is the source of truth.
    capitan_profile: Mapped[CapitanProfile | None] = relationship(
        "CapitanProfile",
        primaryjoin="foreign(Shipment.capitan_id) == CapitanProfile.user_id",
        viewonly=True,
    )
