import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.db.models._enums import BidStatus
from app.schemas.base import BaseSchema


class BidRequest(BaseSchema):
    price: Decimal = Field(gt=0)


class BidRead(BaseSchema):
    bid_id: uuid.UUID
    shipment_id: uuid.UUID
    capitan_id: uuid.UUID
    price: Decimal
    status: BidStatus
    created_at: datetime
    updated_at: datetime


class BidsRead(BaseSchema):
    bids: list[BidRead]
