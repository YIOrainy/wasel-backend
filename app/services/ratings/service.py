import uuid

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyRatedError, NotFoundError, ShipmentNotRatableError
from app.db.models import CapitanProfile, Rating, Shipment
from app.db.models._enums import ShipmentStatus
from app.services.ratings.dal import RatingsDAL


class RatingsService:
    def __init__(self, session: AsyncSession, ratings_dal: RatingsDAL) -> None:
        self.session = session
        self.ratings_dal = ratings_dal

    async def get_for_shipment(self, shipment_id: uuid.UUID) -> Rating:
        rating = await self.ratings_dal.get_by_shipment(shipment_id)
        if rating is None:
            raise NotFoundError("rating not found")
        return rating

    async def get_captain_performance(
        self, capitan_id: uuid.UUID
    ) -> tuple[float, int, list[Rating]]:
        average, total = await self.ratings_dal.get_stats_for_captain(capitan_id)
        reviews = await self.ratings_dal.get_for_captain(capitan_id)
        return average, total, reviews

    async def create(
        self,
        *,
        shipment: Shipment,
        stars: int,
        comment: str | None,
    ) -> Rating:
        if shipment.status != ShipmentStatus.DELIVERED or shipment.capitan_id is None:
            raise ShipmentNotRatableError()

        rating = Rating(
            rating_id=uuid.uuid4(),
            shipment_id=shipment.shipment_id,
            sender_id=shipment.sender_id,
            capitan_id=shipment.capitan_id,
            stars=stars,
            comment=comment,
        )
        try:
            await self.ratings_dal.insert(rating)
        except IntegrityError:
            raise AlreadyRatedError() from None

        await self._refresh_capitan_rating(shipment.capitan_id)
        return rating

    async def _refresh_capitan_rating(self, capitan_id: uuid.UUID) -> None:
        average, _total = await self.ratings_dal.get_stats_for_captain(capitan_id)
        await self.session.execute(
            update(CapitanProfile)
            .where(CapitanProfile.user_id == capitan_id)
            .values(rating=average)
        )
