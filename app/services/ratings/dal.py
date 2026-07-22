import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Rating


class RatingsDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_shipment(self, shipment_id: uuid.UUID) -> Rating | None:
        result = await self.session.execute(
            select(Rating).where(Rating.shipment_id == shipment_id)
        )
        return result.scalar_one_or_none()

    async def get_for_captain(self, capitan_id: uuid.UUID) -> list[Rating]:
        result = await self.session.execute(
            select(Rating)
            .where(Rating.capitan_id == capitan_id)
            .order_by(Rating.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_stats_for_captain(self, capitan_id: uuid.UUID) -> tuple[float, int]:
        result = await self.session.execute(
            select(
                func.coalesce(func.avg(Rating.stars), 0.0),
                func.count(Rating.rating_id),
            ).where(Rating.capitan_id == capitan_id)
        )
        average, total = result.one()
        return float(average), total

    async def insert(self, rating: Rating) -> None:
        self.session.add(rating)
        await self.session.flush()
