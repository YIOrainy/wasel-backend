import uuid
from datetime import datetime

from pydantic import Field

from app.core.schema import BaseSchema


class RatingRequest(BaseSchema):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RatingRead(BaseSchema):
    rating_id: uuid.UUID
    shipment_id: uuid.UUID
    capitan_id: uuid.UUID
    stars: int
    comment: str | None = None
    created_at: datetime


class CaptainPerformance(BaseSchema):
    capitan_id: uuid.UUID
    average_rating: float
    total_ratings: int
    reviews: list[RatingRead]
