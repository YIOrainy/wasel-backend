import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateLocationError
from app.db.models import SavedLocation
from app.services.saved_locations.dal import SavedLocationsDAL


class SavedLocationsService:
    def __init__(
        self, session: AsyncSession, saved_locations_dal: SavedLocationsDAL
    ) -> None:
        self.session = session
        self.saved_locations_dal = saved_locations_dal

    async def list_for_user(self, user_id: uuid.UUID) -> list[SavedLocation]:
        return await self.saved_locations_dal.get_all_for_user(user_id)

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        label: str,
        address_line: str,
        city: str,
        lat: float,
        lng: float,
        notes: str | None,
    ) -> SavedLocation:
        saved_location = SavedLocation(
            saved_location_id=uuid.uuid4(),
            user_id=user_id,
            kind=kind,
            label=label,
            address_line=address_line,
            city=city,
            lat=lat,
            lng=lng,
            notes=notes,
        )
        try:
            await self.saved_locations_dal.insert(saved_location)
            await self.session.commit()
        except IntegrityError:
            # lost the race to a concurrent insert; the unique constraint caught it
            await self.session.rollback()
            raise DuplicateLocationError() from None
        return saved_location

    async def update(
        self,
        saved_location: SavedLocation,
        *,
        kind: str,
        label: str,
        address_line: str,
        city: str,
        lat: float,
        lng: float,
        notes: str | None,
    ) -> SavedLocation:
        saved_location.kind = kind
        saved_location.label = label
        saved_location.address_line = address_line
        saved_location.city = city
        saved_location.lat = lat
        saved_location.lng = lng
        saved_location.notes = notes
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise DuplicateLocationError() from None
        return saved_location

    async def delete(self, saved_location: SavedLocation) -> None:
        await self.saved_locations_dal.delete(saved_location)
        await self.session.commit()
