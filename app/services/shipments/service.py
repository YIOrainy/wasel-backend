from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ShipmentNotAcceptableError
from app.db.models import Bid, Shipment
from app.db.models._enums import BidStatus, ShipmentStatus
from app.realtime.notify import notify, notify_request_feed
from app.schemas.bid import BidRead
from app.schemas.shipment import ShipmentRequest
from app.services.shipments.dal import BidsDAL, ShipmentsDAL

if TYPE_CHECKING:
    # Typed-only import to break the cycle (jobs.py imports this service).
    from app.services.shipments.jobs import ShipmentExpiryDispatcher

# The bidding window: a fresh request is open for offers for this long.
BIDDING_WINDOW = timedelta(hours=1)

# States from which a shipment can no longer change (no cancel, no accept, …).
_TERMINAL = (ShipmentStatus.DELIVERED, ShipmentStatus.EXPIRED, ShipmentStatus.CANCELLED)


class ShipmentsService:
    def __init__(
        self,
        session: AsyncSession,
        shipments_dal: ShipmentsDAL,
        bids_dal: BidsDAL,
        expiry_dispatcher: ShipmentExpiryDispatcher | None = None,
    ) -> None:
        self.session = session
        self.shipments_dal = shipments_dal
        self.bids_dal = bids_dal
        self.expiry_dispatcher = expiry_dispatcher

    async def get_by_id(self, shipment_id: uuid.UUID) -> Shipment:
        shipment = await self.shipments_dal.get_by_id(shipment_id)
        if shipment is None:
            raise NotFoundError("shipment not found")
        return shipment

    async def list_open(self) -> list[Shipment]:
        return await self.shipments_dal.get_open()

    async def list_for_user(
        self, user_id: uuid.UUID, role: str | None = None
    ) -> list[Shipment]:
        return await self.shipments_dal.get_for_user(user_id, role)

    async def list_bids(self, shipment_id: uuid.UUID) -> list[Bid]:
        return await self.bids_dal.get_for_shipment(shipment_id)

    async def list_my_bids(
        self, capitan_id: uuid.UUID, status: BidStatus | None = None
    ) -> list[Bid]:
        return await self.bids_dal.get_for_captain(capitan_id, status)

    async def create(self, *, sender_id: uuid.UUID, data: ShipmentRequest) -> Shipment:
        shipment = Shipment(
            shipment_id=uuid.uuid4(),
            sender_id=sender_id,
            status=ShipmentStatus.PENDING,
            expires_at=datetime.now(UTC) + BIDDING_WINDOW,
            # price stays NULL until a bid is accepted
            **data.model_dump(),
        )
        await self.shipments_dal.insert(shipment)
        # Enqueue the expiry job on this same connection BEFORE commit
        if self.expiry_dispatcher is not None:
            await self.expiry_dispatcher.enqueue_expiry(self.session, shipment)
        await self.session.commit()
        # Thin broadcast — captains refetch the open list (no receiver PII pushed).
        await notify_request_feed(
            "new_request",
            {
                "shipment_id": str(shipment.shipment_id),
                "pickup_city": shipment.pickup_city,
                "destination_city": shipment.destination_city,
            },
        )
        return shipment

    async def place_bid(
        self, *, shipment_id: uuid.UUID, capitan_id: uuid.UUID, price: Decimal
    ) -> Bid:
        shipment = await self.shipments_dal.get_by_id(shipment_id)
        if shipment is None:
            raise NotFoundError("shipment not found")
        if shipment.status != ShipmentStatus.PENDING or shipment.expires_at <= datetime.now(UTC):
            raise ShipmentNotAcceptableError()

        stmt = (
            pg_insert(Bid)
            .values(
                bid_id=uuid.uuid4(),
                shipment_id=shipment_id,
                capitan_id=capitan_id,
                price=price,
                status=BidStatus.PENDING,
            )
            .on_conflict_do_update(
                index_elements=["shipment_id", "capitan_id"],
                set_={"price": price},
            )
            .returning(Bid)
        )
        # populate_existing: if this captain's bid is already in the identity map
        # (re-bid in the same session), overwrite it with the returned row so the
        # price we hand back is the DB truth, not the stale in-memory value.
        bid = (
            await self.session.execute(
                stmt, execution_options={"populate_existing": True}
            )
        ).scalar_one()
        await self.session.commit()
        await notify(
            shipment.sender_id,
            "new_bid",
            {"bid": BidRead.model_validate(bid).model_dump(mode="json")},
        )
        return bid

    async def accept_bid(
        self, *, shipment_id: uuid.UUID, bid_id: uuid.UUID, sender_id: uuid.UUID
    ) -> Shipment:
        bid_row = (
            await self.session.execute(
                update(Bid)
                .where(
                    Bid.bid_id == bid_id,
                    Bid.shipment_id == shipment_id,
                    Bid.status == BidStatus.PENDING,
                )
                .values(status=BidStatus.ACCEPTED)
                .returning(Bid.capitan_id, Bid.price)
            )
        ).first()
        if bid_row is None:
            await self.session.rollback()
            bid = await self.bids_dal.get_by_id(bid_id)
            if bid is None or bid.shipment_id != shipment_id:
                raise NotFoundError("bid not found") 
            raise ShipmentNotAcceptableError()  # already decided
        capitan_id, price = bid_row

        result = await self.session.execute(
            update(Shipment)
            .where(
                Shipment.shipment_id == shipment_id,
                Shipment.sender_id == sender_id,
                Shipment.status == ShipmentStatus.PENDING,
                Shipment.expires_at > func.now(),
            )
            .values(
                status=ShipmentStatus.ACCEPTED,
                capitan_id=capitan_id,
                price=price,  # snapshot the agreed price
                accepted_at=func.now(),
            )
        )
        if result.rowcount == 0:
            await self.session.rollback()
            raise ShipmentNotAcceptableError()

        await self.session.execute(
            update(Bid)
            .where(
                Bid.shipment_id == shipment_id,
                Bid.bid_id != bid_id,
                Bid.status == BidStatus.PENDING,
            )
            .values(status=BidStatus.REJECTED)
        )
        await self.session.commit()
        for sibling in await self.bids_dal.get_for_shipment(shipment_id):
            event = (
                "bid_accepted"
                if sibling.status == BidStatus.ACCEPTED
                else "bid_rejected"
            )
            await notify(
                sibling.capitan_id,
                event,
                {"shipment_id": str(shipment_id), "bid_id": str(sibling.bid_id)},
            )
        return await self.get_by_id(shipment_id)

    async def expire(self, shipment_id: uuid.UUID) -> uuid.UUID | None:
        result = await self.session.execute(
            update(Shipment)
            .where(
                Shipment.shipment_id == shipment_id,
                Shipment.status == ShipmentStatus.PENDING,
                Shipment.expires_at <= func.now(),
            )
            .values(status=ShipmentStatus.EXPIRED)
            .returning(Shipment.sender_id)
        )
        await self.session.commit()
        row = result.first()
        return row[0] if row else None

    async def cancel(self, shipment_id: uuid.UUID) -> Shipment:
        result = await self.session.execute(
            update(Shipment)
            .where(
                Shipment.shipment_id == shipment_id,
                Shipment.status.not_in(_TERMINAL),
            )
            .values(status=ShipmentStatus.CANCELLED)
        )
        if result.rowcount == 0:
            await self.session.rollback()
            # distinguish "not there" from "already terminal"
            if await self.shipments_dal.get_by_id(shipment_id) is None:
                raise NotFoundError("shipment not found")
            raise ShipmentNotAcceptableError()
        await self.session.commit()
        return await self.get_by_id(shipment_id)

    async def cancel_by_sender(
        self, shipment_id: uuid.UUID, sender_id: uuid.UUID
    ) -> Shipment:
        result = await self.session.execute(
            update(Shipment)
            .where(
                Shipment.shipment_id == shipment_id,
                Shipment.sender_id == sender_id,
                Shipment.status == ShipmentStatus.PENDING,
            )
            .values(status=ShipmentStatus.CANCELLED)
        )
        if result.rowcount == 0:
            await self.session.rollback()
            shipment = await self.shipments_dal.get_by_id(shipment_id)
            if shipment is None or shipment.sender_id != sender_id:
                raise NotFoundError("shipment not found")  # not theirs / missing
            raise ShipmentNotAcceptableError()  # no longer pending
        await self.session.commit()
        return await self.get_by_id(shipment_id)

    async def withdraw_bid(
        self, *, shipment_id: uuid.UUID, bid_id: uuid.UUID, capitan_id: uuid.UUID
    ) -> None:
        result = await self.session.execute(
            delete(Bid).where(
                Bid.bid_id == bid_id,
                Bid.shipment_id == shipment_id,
                Bid.capitan_id == capitan_id,
                Bid.status == BidStatus.PENDING,
            )
        )
        if result.rowcount == 0:
            await self.session.rollback()
            bid = await self.bids_dal.get_by_id(bid_id)
            if bid is None or bid.capitan_id != capitan_id or bid.shipment_id != shipment_id:
                raise NotFoundError("bid not found")  # not theirs / missing
            raise ShipmentNotAcceptableError()  # accepted/rejected → can't withdraw
        await self.session.commit()
