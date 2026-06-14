import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedLocation


class SavedLocationsDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, saved_location_id: uuid.UUID) -> SavedLocation | None:
        result = await self.session.execute(
            select(SavedLocation).where(
                SavedLocation.saved_location_id == saved_location_id
            )
        )
        return result.scalar_one_or_none()

    async def get_all_for_user(self, user_id: uuid.UUID) -> list[SavedLocation]:
        result = await self.session.execute(
            select(SavedLocation)
            .where(SavedLocation.user_id == user_id)
            .order_by(SavedLocation.created_at)
        )
        return list(result.scalars().all())

    async def insert(self, saved_location: SavedLocation) -> None:
        self.session.add(saved_location)
        await self.session.flush()

    async def delete(self, saved_location: SavedLocation) -> None:
        await self.session.delete(saved_location)
        await self.session.flush()
