from fastapi import APIRouter, status

from app.entrypoints.api.deps import (
    CurrentUser,
    OwnedSavedLocation,
    SavedLocationsServiceDep,
)
from app.schemas.saved_location import (
    SavedLocationEntry,
    SavedLocationRead,
    SavedLocationsRead,
)

router = APIRouter(prefix="/saved-locations", tags=["saved-locations"])


@router.get("", response_model=SavedLocationsRead)
async def list_saved_locations(
    user: CurrentUser, saved_locations_service: SavedLocationsServiceDep
) -> SavedLocationsRead:
    locations = await saved_locations_service.list_for_user(user.user_id)
    return SavedLocationsRead(
        saved_locations=[SavedLocationRead.model_validate(loc) for loc in locations]
    )


@router.post("", response_model=SavedLocationRead, status_code=status.HTTP_201_CREATED)
async def create_saved_location(
    payload: SavedLocationEntry,
    user: CurrentUser,
    saved_locations_service: SavedLocationsServiceDep,
) -> SavedLocationRead:
    location = await saved_locations_service.create(
        user_id=user.user_id,
        kind=payload.kind,
        label=payload.label,
        address_line=payload.address_line,
        city=payload.city,
        lat=payload.lat,
        lng=payload.lng,
        notes=payload.notes,
    )
    return SavedLocationRead.model_validate(location)


@router.get("/{saved_location_id}", response_model=SavedLocationRead)
async def get_saved_location(location: OwnedSavedLocation) -> SavedLocationRead:
    return SavedLocationRead.model_validate(location)


@router.put("/{saved_location_id}", response_model=SavedLocationRead)
async def update_saved_location(
    payload: SavedLocationEntry,
    location: OwnedSavedLocation,
    saved_locations_service: SavedLocationsServiceDep,
) -> SavedLocationRead:
    updated = await saved_locations_service.update(
        location,
        kind=payload.kind,
        label=payload.label,
        address_line=payload.address_line,
        city=payload.city,
        lat=payload.lat,
        lng=payload.lng,
        notes=payload.notes,
    )
    return SavedLocationRead.model_validate(updated)


@router.delete("/{saved_location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_location(
    location: OwnedSavedLocation,
    saved_locations_service: SavedLocationsServiceDep,
) -> None:
    await saved_locations_service.delete(location)
