import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class UserRead(BaseSchema):
    id: uuid.UUID = Field(validation_alias="user_id")
    name: str
    phone: str = Field(validation_alias="phone_number")
    email: str | None = None
    avatar_url: str | None = None
    is_captain: bool = False
    created_at: datetime
