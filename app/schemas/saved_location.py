import uuid
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema

# Allowed values for a saved location's `kind`. Mirrors the model comment.
SavedLocationKind = Literal["home", "work", "other"]


class SavedLocationEntry(BaseSchema):
    kind: SavedLocationKind
    label: str = Field(min_length=1, max_length=80)
    address_line: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=500)


class SavedLocationRead(SavedLocationEntry):
    saved_location_id: uuid.UUID


class SavedLocationsRead(BaseSchema):
    saved_locations: list[SavedLocationRead]
