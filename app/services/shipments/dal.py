import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, Shipment
from app.db.models._enums import BidStatus, ShipmentStatus


class ShipmentsDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, shipment_id: uuid.UUID) -> Shipment | None:
        result = await self.session.execute(
            select(Shipment).where(Shipment.shipment_id == shipment_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(
        self, user_id: uuid.UUID, role: str | None = None
    ) -> list[Shipment]:
        """The caller's shipments, all statuses, newest first. role 'sender' →
        ones they created; 'captain' → ones assigned to them; None → both."""
        if role == "sender":
            where = Shipment.sender_id == user_id
        elif role == "captain":
            where = Shipment.capitan_id == user_id
        else:
            where = or_(Shipment.sender_id == user_id, Shipment.capitan_id == user_id)
        result = await self.session.execute(
            select(Shipment).where(where).order_by(Shipment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_open(self) -> list[Shipment]:
        """Pending shipments still inside their bidding window — the captain
        browse feed. Expired rows fall out via the expires_at filter; visibility
        needs no job."""
        result = await self.session.execute(
            select(Shipment)
            .where(
                Shipment.status == ShipmentStatus.PENDING,
                Shipment.expires_at > func.now(),
            )
            .order_by(Shipment.created_at)
        )
        return list(result.scalars().all())

    async def insert(self, shipment: Shipment) -> None:
        self.session.add(shipment)
        await self.session.flush()


class BidsDAL:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, bid_id: uuid.UUID) -> Bid | None:
        result = await self.session.execute(select(Bid).where(Bid.bid_id == bid_id))
        return result.scalar_one_or_none()

    async def get_for_shipment(self, shipment_id: uuid.UUID) -> list[Bid]:
        result = await self.session.execute(
            select(Bid).where(Bid.shipment_id == shipment_id).order_by(Bid.created_at)
        )
        return list(result.scalars().all())

    async def get_for_captain(
        self, capitan_id: uuid.UUID, status: BidStatus | None = None
    ) -> list[Bid]:
        """A captain's own bids, newest first; optional status filter."""
        stmt = select(Bid).where(Bid.capitan_id == capitan_id)
        if status is not None:
            stmt = stmt.where(Bid.status == status)
        result = await self.session.execute(stmt.order_by(Bid.created_at.desc()))
        return list(result.scalars().all())

    async def insert(self, bid: Bid) -> None:
        self.session.add(bid)
        await self.session.flush()
