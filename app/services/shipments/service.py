from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from secrets import randbelow
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidShipmentOtpError,
    NotFoundError,
    ShipmentNotAcceptableError,
)
from app.db.models import Bid, Shipment
from app.db.models._enums import BidStatus, ShipmentStatus
from app.realtime.notify import notify, notify_request_feed
from app.services.shipments.schemas import BidRead
from app.services.shipments.schemas import ShipmentRequest
from app.services.shipments.dal import BidsDAL, ShipmentsDAL

if TYPE_CHECKING:
    # Typed-only import to break the cycle (jobs.py imports this service).
    from app.services.shipments.jobs import ShipmentExpiryDispatcher


# The bidding window: a fresh request is open for offers for this long.
BIDDING_WINDOW = timedelta(hours=1)

# States from which a shipment can no longer change.
_TERMINAL = (
    ShipmentStatus.DELIVERED,
    ShipmentStatus.EXPIRED,
    ShipmentStatus.CANCELLED,
)


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
        self,
        user_id: uuid.UUID,
        role: str | None = None,
    ) -> list[Shipment]:
        return await self.shipments_dal.get_for_user(user_id, role)

    async def list_bids(self, shipment_id: uuid.UUID) -> list[Bid]:
        return await self.bids_dal.get_for_shipment(shipment_id)

    async def list_my_bids(
        self,
        capitan_id: uuid.UUID,
        status: BidStatus | None = None,
    ) -> list[Bid]:
        return await self.bids_dal.get_for_captain(capitan_id, status)

    async def create(
        self,
        *,
        sender_id: uuid.UUID,
        data: ShipmentRequest,
    ) -> Shipment:
        shipment = Shipment(
            shipment_id=uuid.uuid4(),
            sender_id=sender_id,
            status=ShipmentStatus.PENDING,
            expires_at=datetime.now(UTC) + BIDDING_WINDOW,
            # price stays NULL until a bid is accepted
            pickup_otp=f"{randbelow(10000):04d}",
            delivery_otp=f"{randbelow(10000):04d}",
            **data.model_dump(),
        )

        await self.shipments_dal.insert(shipment)

        # Enqueue the expiry job on this same connection BEFORE commit.
        if self.expiry_dispatcher is not None:
            await self.expiry_dispatcher.enqueue_expiry(self.session, shipment)

        # Note: this still happens before commit. For production reliability,
        # consider an outbox pattern later.
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
        self,
        *,
        shipment_id: uuid.UUID,
        capitan_id: uuid.UUID,
        price: Decimal,
    ) -> Bid:
        shipment = await self.shipments_dal.get_by_id(shipment_id)

        if shipment is None:
            raise NotFoundError("shipment not found")

        if (
            shipment.status != ShipmentStatus.PENDING
            or shipment.expires_at <= datetime.now(UTC)
        ):
            raise ShipmentNotAcceptableError()

        insert_stmt = pg_insert(Bid).values(
            bid_id=uuid.uuid4(),
            shipment_id=shipment_id,
            capitan_id=capitan_id,
            price=price,
            status=BidStatus.PENDING,
        )

        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[Bid.shipment_id, Bid.capitan_id],
            set_={
                "price": insert_stmt.excluded.price,
            },
            # Important:
            # If the existing bid is already ACCEPTED or REJECTED,
            # do not allow re-pricing it.
            where=(Bid.status == BidStatus.PENDING),
        ).returning(Bid)

        bid = (
            await self.session.execute(
                stmt,
                execution_options={"populate_existing": True},
            )
        ).scalar_one_or_none()

        if bid is None:
            raise ShipmentNotAcceptableError("bid can no longer be updated")

        # RETURNING gives a Bid with no loaded captain; serializing it would
        # lazy-load (→ async crash). Re-fetch with the captain+profile eager.
        bid = await self.bids_dal.get_by_id(bid.bid_id)

        await notify(
            shipment.sender_id,
            "new_bid",
            {
                # by_alias=True → camelCase, matching the HTTP responses the
                # client parses with (FastAPI serializes responses by_alias).
                "bid": BidRead.model_validate(bid).model_dump(mode="json", by_alias=True),
            },
        )

        return bid

    async def accept_bid(
        self,
        *,
        shipment_id: uuid.UUID,
        bid_id: uuid.UUID,
        sender_id: uuid.UUID,
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
            bid = await self.bids_dal.get_by_id(bid_id)

            if bid is None or bid.shipment_id != shipment_id:
                raise NotFoundError("bid not found")

            raise ShipmentNotAcceptableError("bid is already decided")

        capitan_id, price = bid_row

        shipment = (
            await self.session.execute(
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
                .returning(Shipment),
                execution_options={"populate_existing": True},
            )
        ).scalar_one_or_none()

        if shipment is None:
            raise ShipmentNotAcceptableError()

        rejected_bids = (
            await self.session.execute(
                update(Bid)
                .where(
                    Bid.shipment_id == shipment_id,
                    Bid.bid_id != bid_id,
                    Bid.status == BidStatus.PENDING,
                )
                .values(status=BidStatus.REJECTED)
                .returning(Bid.capitan_id, Bid.bid_id)
            )
        ).all()

        await notify(
            capitan_id,
            "bid_accepted",
            {
                "shipment_id": str(shipment_id),
                "bid_id": str(bid_id),
            },
        )

        for rejected_capitan_id, rejected_bid_id in rejected_bids:
            await notify(
                rejected_capitan_id,
                "bid_rejected",
                {
                    "shipment_id": str(shipment_id),
                    "bid_id": str(rejected_bid_id),
                },
            )

        # Drop the now-assigned shipment from every captain's open feed (winner,
        # losers, and captains who never bid).
        await notify_request_feed("request_closed", {"shipment_id": str(shipment_id)})

        # Re-fetch so the now-assigned captain is eager-loaded for serialization.
        return await self.shipments_dal.get_by_id(shipment_id)

    async def expire(self, shipment_id: uuid.UUID) -> uuid.UUID | None:
        row = (
            await self.session.execute(
                update(Shipment)
                .where(
                    Shipment.shipment_id == shipment_id,
                    Shipment.status == ShipmentStatus.PENDING,
                    Shipment.expires_at <= func.now(),
                )
                .values(status=ShipmentStatus.EXPIRED)
                .returning(Shipment.sender_id)
            )
        ).first()

        return row[0] if row else None

    async def cancel(self, shipment_id: uuid.UUID) -> Shipment:
        shipment = (
            await self.session.execute(
                update(Shipment)
                .where(
                    Shipment.shipment_id == shipment_id,
                    Shipment.status.not_in(_TERMINAL),
                )
                .values(status=ShipmentStatus.CANCELLED)
                .returning(Shipment),
                execution_options={"populate_existing": True},
            )
        ).scalar_one_or_none()

        if shipment is not None:
            # ponytail: harmless no-op refetch if it wasn't open (already accepted).
            await notify_request_feed("request_closed", {"shipment_id": str(shipment_id)})
            return await self.shipments_dal.get_by_id(shipment_id)

        # Failure-only query: used to distinguish "missing" from "already terminal".
        existing_shipment = await self.shipments_dal.get_by_id(shipment_id)

        if existing_shipment is None:
            raise NotFoundError("shipment not found")

        raise ShipmentNotAcceptableError()

    async def cancel_by_sender(
        self,
        shipment_id: uuid.UUID,
        sender_id: uuid.UUID,
    ) -> Shipment:
        shipment = (
            await self.session.execute(
                update(Shipment)
                .where(
                    Shipment.shipment_id == shipment_id,
                    Shipment.sender_id == sender_id,
                    Shipment.status == ShipmentStatus.PENDING,
                )
                .values(status=ShipmentStatus.CANCELLED)
                .returning(Shipment),
                execution_options={"populate_existing": True},
            )
        ).scalar_one_or_none()

        if shipment is not None:
            await notify_request_feed("request_closed", {"shipment_id": str(shipment_id)})
            return await self.shipments_dal.get_by_id(shipment_id)

        existing_shipment = await self.shipments_dal.get_by_id(shipment_id)

        if existing_shipment is None or existing_shipment.sender_id != sender_id:
            raise NotFoundError("shipment not found")

        raise ShipmentNotAcceptableError("shipment is no longer pending")

    async def withdraw_bid(
        self,
        *,
        shipment_id: uuid.UUID,
        bid_id: uuid.UUID,
        capitan_id: uuid.UUID,
    ) -> None:
        deleted_bid_id = (
            await self.session.execute(
                delete(Bid)
                .where(
                    Bid.bid_id == bid_id,
                    Bid.shipment_id == shipment_id,
                    Bid.capitan_id == capitan_id,
                    Bid.status == BidStatus.PENDING,
                )
                .returning(Bid.bid_id)
            )
        ).scalar_one_or_none()

        if deleted_bid_id is not None:
            return

        bid = await self.bids_dal.get_by_id(bid_id)

        if (
            bid is None
            or bid.capitan_id != capitan_id
            or bid.shipment_id != shipment_id
        ):
            raise NotFoundError("bid not found")

        raise ShipmentNotAcceptableError("bid can no longer be withdrawn")

    async def mark_picked_up(self, *, shipment: Shipment, otp: str) -> Shipment:
        if shipment.status != ShipmentStatus.ACCEPTED:
            raise ShipmentNotAcceptableError("shipment is not accepted")
        if shipment.pickup_otp != otp:
            raise InvalidShipmentOtpError()
        await self.shipments_dal.update_status(
            shipment, ShipmentStatus.PICKED, "picked_at"
        )
        await notify(
            shipment.sender_id,
            "shipment_picked",
            {"shipment_id": str(shipment.shipment_id)},
        )
        return shipment

    async def mark_out_for_delivery(self, *, shipment: Shipment) -> Shipment:
        if shipment.status != ShipmentStatus.PICKED:
            raise ShipmentNotAcceptableError("shipment is not picked up")
        await self.shipments_dal.update_status(
            shipment, ShipmentStatus.OUT_FOR_DELIVERY, "out_for_delivery_at"
        )
        await notify(
            shipment.sender_id,
            "shipment_out_for_delivery",
            {"shipment_id": str(shipment.shipment_id)},
        )
        return shipment

    async def mark_delivered(self, *, shipment: Shipment, otp: str) -> Shipment:
        # TODO: gate on captain GPS within a radius of the destination.
        if shipment.status != ShipmentStatus.OUT_FOR_DELIVERY:
            raise ShipmentNotAcceptableError("shipment is not out for delivery")
        if shipment.delivery_otp != otp:
            raise InvalidShipmentOtpError()
        await self.shipments_dal.update_status(
            shipment, ShipmentStatus.DELIVERED, "delivered_at"
        )
        await notify(
            shipment.sender_id,
            "shipment_delivered",
            {"shipment_id": str(shipment.shipment_id)},
        )
        return shipment