import uuid

from fastapi import APIRouter, status

from app.entrypoints.api.deps import (
    CurrentUser,
    OwnedShipment,
    RatingsServiceDep,
    ViewableShipment,
)
from app.services.ratings.schemas import CaptainPerformance, RatingRead, RatingRequest

router = APIRouter(tags=["ratings"])


@router.post(
    "/shipments/{shipment_id}/rating",
    response_model=RatingRead,
    status_code=status.HTTP_201_CREATED,
)
async def rate_shipment(
    payload: RatingRequest,
    shipment: OwnedShipment,
    service: RatingsServiceDep,
) -> RatingRead:
    """Sender leaves a rating for a delivered shipment's captain. One per
    shipment (409 if already rated, 409 if not yet delivered)."""
    rating = await service.create(
        shipment=shipment, stars=payload.stars, comment=payload.comment
    )
    return RatingRead.model_validate(rating)


@router.get("/shipments/{shipment_id}/rating", response_model=RatingRead)
async def get_shipment_rating(
    shipment: ViewableShipment, service: RatingsServiceDep
) -> RatingRead:
    """Sender or assigned captain only (else 404). 404 if not yet rated."""
    rating = await service.get_for_shipment(shipment.shipment_id)
    return RatingRead.model_validate(rating)


@router.get("/captains/{capitan_id}/ratings", response_model=CaptainPerformance)
async def get_captain_performance(
    capitan_id: uuid.UUID,
    _user: CurrentUser,
    service: RatingsServiceDep,
) -> CaptainPerformance:
    """A captain's accumulated performance: average rating, review count, and
    the full review history — used to display captain performance to senders."""
    average, total, reviews = await service.get_captain_performance(capitan_id)
    return CaptainPerformance(
        capitan_id=capitan_id,
        average_rating=average,
        total_ratings=total,
        reviews=[RatingRead.model_validate(r) for r in reviews],
    )
