import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import AwareDatetime, Field, field_validator

from app.core.schema import BaseSchema
from app.db.models._enums import BidStatus, DeliveryMode, ShipmentStatus
from app.services.users.schemas import CaptainPublic


class BidRequest(BaseSchema):
    price: Decimal = Field(gt=0)
    promised_delivery_time: AwareDatetime

    @field_validator("promised_delivery_time")
    @classmethod
    def _promise_in_future(cls, value: datetime) -> datetime:
        if value <= datetime.now(UTC):
            raise ValueError("promisedDeliveryTime must be in the future")
        return value


class BidRead(BaseSchema):
    bid_id: uuid.UUID
    shipment_id: uuid.UUID
    capitan: CaptainPublic
    price: Decimal
    promised_delivery_time: datetime
    status: BidStatus
    created_at: datetime
    updated_at: datetime


class BidsRead(BaseSchema):
    bids: list[BidRead]


class ShipmentRequest(BaseSchema):
    pickup_city: str = Field(min_length=1, max_length=80)
    destination_city: str = Field(min_length=1, max_length=80)
    pickup_lat: float = Field(ge=-90, le=90)
    pickup_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    receiver_phone_number: str | None = Field(default=None, max_length=20)
    delivery_mode: DeliveryMode
    special_handling: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=2048)


class ShipmentRead(ShipmentRequest):
    shipment_id: uuid.UUID
    sender_id: uuid.UUID
    capitan: CaptainPublic | None = None
    status: ShipmentStatus
    price: Decimal | None = None
    promised_delivery_time: datetime | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None
    picked_at: datetime | None = None
    out_for_delivery_at: datetime | None = None
    delivered_at: datetime | None = None


class ShipmentsRead(BaseSchema):
    shipments: list[ShipmentRead]


class ShipmentOtpRequest(BaseSchema):
    otp: str = Field(min_length=1, max_length=10)


class ShipmentOtps(BaseSchema):
    pickup_otp: str | None = None
    delivery_otp: str | None = None
