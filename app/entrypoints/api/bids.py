from fastapi import APIRouter

from app.db.models._enums import BidStatus
from app.entrypoints.api.deps import CurrentCaptain, ShipmentsServiceDep
from app.schemas.bid import BidRead, BidsRead

router = APIRouter(prefix="/bids", tags=["bids"])


@router.get("", response_model=BidsRead)
async def my_bids(
    captain: CurrentCaptain,
    service: ShipmentsServiceDep,
    status: BidStatus | None = None,
) -> BidsRead:
    """The authenticated captain's own bids, newest first; optional status filter."""
    bids = await service.list_my_bids(captain.user_id, status)
    return BidsRead(bids=[BidRead.model_validate(b) for b in bids])
