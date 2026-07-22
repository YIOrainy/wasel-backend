import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Rating(Base):
    __tablename__ = "ratings"

    rating_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("shipments.shipment_id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    capitan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
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

    __table_args__ = (
        # One review per shipment — a shipment has exactly one sender/captain pair.
        UniqueConstraint("shipment_id", name="uq_ratings_shipment"),
        CheckConstraint("stars BETWEEN 1 AND 5", name="ck_ratings_stars_range"),
    )
