import uuid
from typing import Literal

from fastapi import APIRouter, status

from app.entrypoints.api.deps import (
    CurrentCaptain,
    CurrentUser,
    OwnedShipment,
    ShipmentsServiceDep,
    ViewableShipment,
)
from app.schemas.bid import BidRead, BidRequest, BidsRead
from app.schemas.shipment import ShipmentRead, ShipmentRequest, ShipmentsRead

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.post("", response_model=ShipmentRead, status_code=status.HTTP_201_CREATED)
async def create_shipment(
    payload: ShipmentRequest, user: CurrentUser, service: ShipmentsServiceDep
) -> ShipmentRead:
    shipment = await service.create(sender_id=user.user_id, data=payload)
    return ShipmentRead.model_validate(shipment)


@router.get("", response_model=ShipmentsRead)
async def my_shipments(
    user: CurrentUser,
    service: ShipmentsServiceDep,
    role: Literal["sender", "captain"] | None = None,
) -> ShipmentsRead:
    """The caller's shipments, all statuses, newest first. role=sender → ones
    they requested; role=captain → ones they're delivering; omitted → both."""
    shipments = await service.list_for_user(user.user_id, role)
    return ShipmentsRead(shipments=[ShipmentRead.model_validate(s) for s in shipments])


@router.get("/open", response_model=ShipmentsRead)
async def browse_open_shipments(
    _captain: CurrentCaptain, service: ShipmentsServiceDep
) -> ShipmentsRead:
    """Captains browse open requests to bid on (any city — inter-city delivery)."""
    shipments = await service.list_open()
    # ponytail: browse returns full ShipmentRead incl. receiver_phone_number —
    # deliberate (captains see it). Slim it only if receiver PII becomes a concern.
    return ShipmentsRead(shipments=[ShipmentRead.model_validate(s) for s in shipments])


@router.get("/{shipment_id}", response_model=ShipmentRead)
async def get_shipment(shipment: ViewableShipment) -> ShipmentRead:
    """Sender or assigned captain only (else 404)."""
    return ShipmentRead.model_validate(shipment)


@router.get("/{shipment_id}/bids", response_model=BidsRead)
async def list_bids(shipment: OwnedShipment, service: ShipmentsServiceDep) -> BidsRead:
    """The bid snapshot — owner only. SSE streams deltas on top of this."""
    bids = await service.list_bids(shipment.shipment_id)
    return BidsRead(bids=[BidRead.model_validate(b) for b in bids])


@router.post(
    "/{shipment_id}/bids",
    response_model=BidRead,
    status_code=status.HTTP_201_CREATED,
)
async def place_bid(
    shipment_id: uuid.UUID,
    payload: BidRequest,
    captain: CurrentCaptain,
    service: ShipmentsServiceDep,
) -> BidRead:
    """Captains only. Upsert — re-bidding updates the price (409 if not open)."""
    bid = await service.place_bid(
        shipment_id=shipment_id, capitan_id=captain.user_id, price=payload.price
    )
    return BidRead.model_validate(bid)


@router.post("/{shipment_id}/bids/{bid_id}/accept", response_model=ShipmentRead)
async def accept_bid(
    bid_id: uuid.UUID, shipment: OwnedShipment, service: ShipmentsServiceDep
) -> ShipmentRead:
    """Owner accepts an offer. OwnedShipment gives the 404/privacy layer; the
    service's atomic gate is the race-proof boundary (409 on a lost race)."""
    updated = await service.accept_bid(
        shipment_id=shipment.shipment_id,
        bid_id=bid_id,
        sender_id=shipment.sender_id,
    )
    return ShipmentRead.model_validate(updated)


@router.delete(
    "/{shipment_id}/bids/{bid_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def withdraw_bid(
    shipment_id: uuid.UUID,
    bid_id: uuid.UUID,
    captain: CurrentCaptain,
    service: ShipmentsServiceDep,
) -> None:
    """A captain withdraws their own bid — only while pending (404 if not theirs,
    409 if already accepted/rejected)."""
    await service.withdraw_bid(
        shipment_id=shipment_id, bid_id=bid_id, capitan_id=captain.user_id
    )


@router.post("/{shipment_id}/cancel", response_model=ShipmentRead)
async def cancel_shipment(
    shipment_id: uuid.UUID, user: CurrentUser, service: ShipmentsServiceDep
) -> ShipmentRead:
    if user.role == "admin":
        updated = await service.cancel(shipment_id)
    else:
        updated = await service.cancel_by_sender(shipment_id, user.user_id)
    return ShipmentRead.model_validate(updated)
