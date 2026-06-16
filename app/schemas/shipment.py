import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.db.models._enums import ShipmentStatus
from app.schemas.base import BaseSchema


class ShipmentRequest(BaseSchema):
    pickup_city: str = Field(min_length=1, max_length=80)
    destination_city: str = Field(min_length=1, max_length=80)
    pickup_lat: float = Field(ge=-90, le=90)
    pickup_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    receiver_phone_number: str | None = Field(default=None, max_length=20)
    expected_pickup_time: datetime
    expected_delivery_time: datetime
    pickup_asap: bool = False
    special_handling: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=2048)


class ShipmentRead(ShipmentRequest):
    shipment_id: uuid.UUID
    sender_id: uuid.UUID
    capitan_id: uuid.UUID | None = None
    status: ShipmentStatus
    price: Decimal | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None
    picked_at: datetime | None = None
    out_for_delivery_at: datetime | None = None
    delivered_at: datetime | None = None


class ShipmentsRead(BaseSchema):
    shipments: list[ShipmentRead]
