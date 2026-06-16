from fastapi import APIRouter, status

from app.entrypoints.api.deps import CurrentUser, DevicesServiceDep
from app.schemas.device import DeviceRead, DeviceRequest

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRequest, user: CurrentUser, service: DevicesServiceDep
) -> DeviceRead:
    """Register/refresh this device's push token (upsert; reassigns on re-login)."""
    device = await service.register(
        user_id=user.user_id, fcm_token=payload.fcm_token, platform=payload.platform
    )
    return DeviceRead.model_validate(device)


@router.delete("/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    fcm_token: str, user: CurrentUser, service: DevicesServiceDep
) -> None:
    """Logout — release this token. Idempotent (204 even if already gone)."""
    await service.unregister(user_id=user.user_id, fcm_token=fcm_token)
