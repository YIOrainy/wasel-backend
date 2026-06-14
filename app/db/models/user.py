from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.capitan_profile import CapitanProfile
    from app.db.models.saved_location import SavedLocation
    from app.db.models.shipment import Shipment


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=True, unique=True)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=False, unique=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
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

    # One-to-one: a user becomes a captain by gaining a profile row.
    capitan_profile: Mapped[CapitanProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    # Shipments this user created (as the sender). Disambiguated by FK because
    # both sender_id and capitan_id point at users.
    shipments_sent: Mapped[list[Shipment]] = relationship(
        back_populates="sender",
        foreign_keys="Shipment.sender_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Shipments this user is delivering (as the assigned captain).
    shipments_assigned: Mapped[list[Shipment]] = relationship(
        back_populates="capitan",
        foreign_keys="Shipment.capitan_id",
        passive_deletes=True,
    )
    # Addresses this user has saved (home, work, …).
    saved_locations: Mapped[list[SavedLocation]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_captain(self) -> bool:
        """A user is a captain iff they have a profile. Requires capitan_profile
        to be eager-loaded (async can't lazy-load on attribute access)."""
        return self.capitan_profile is not None
