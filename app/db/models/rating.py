import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class Rating(Base):
    __tablename__ = "ratings"

    rating_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        nullable=False,
    )
    capitan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        nullable=False,
    )
    stars: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)

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
