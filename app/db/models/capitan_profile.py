from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.shipment import Shipment
    from app.db.models.user import User


class CapitanProfile(Base):
    __tablename__ = "capitan_profiles"

    capitan_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rating: Mapped[float] = mapped_column(nullable=False, default=0.0)
    total_trips: Mapped[int] = mapped_column(nullable=False, default=0)
    # TODO: Add Nafath stuff
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

    user: Mapped[User] = relationship(back_populates="capitan_profile")

    # Convenience: shipments this captain delivers. There's no FK from shipments
    # to this table (capitan_id -> users), so we join on the shared user_id.
    # view-only: persistence is owned by Shipment.capitan / capitan_id.
    shipments: Mapped[list[Shipment]] = relationship(
        "Shipment",
        primaryjoin="CapitanProfile.user_id == foreign(Shipment.capitan_id)",
        viewonly=True,
    )
