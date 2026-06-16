import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema

DevicePlatform = Literal["ios", "android"]


class DeviceRequest(BaseSchema):
    """What the app sends to register/refresh its push channel. The user is the
    authenticated caller (JWT) — never in the body."""

    fcm_token: str = Field(min_length=1, max_length=4096)
    platform: DevicePlatform


class DeviceRead(BaseSchema):
    # No token echo — it's the push address, nothing the client needs back.
    device_id: uuid.UUID
    platform: DevicePlatform
    created_at: datetime
    updated_at: datetime
