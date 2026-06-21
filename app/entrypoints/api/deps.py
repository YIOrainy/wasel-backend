
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidTokenError,
    NotFoundError,
    PermissionDeniedError,
    PhoneAlreadyExistsError,
)
from app.core.security import decode_registration_token, decode_user_token
from app.db.base import AsyncSessionLocal
from app.db.models import SavedLocation, Shipment, User
from app.db.models._enums import ShipmentStatus
from app.services.auth.auth_service import AuthService
from app.services.auth.otp.service import OtpService, build_otp_service
from app.services.devices.dal import DevicesDAL
from app.services.devices.service import DevicesService
from app.services.saved_locations.dal import SavedLocationsDAL
from app.services.saved_locations.service import SavedLocationsService
from app.services.shipments.dal import BidsDAL, ShipmentsDAL
from app.services.shipments.jobs import ShipmentExpiryDispatcher
from app.services.shipments.service import ShipmentsService
from app.services.users.dal import UsersDAL
from app.services.users.service import UsersService


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_users_dal(session: SessionDep) -> UsersDAL:
    return UsersDAL(session)


UsersDALDep = Annotated[UsersDAL, Depends(get_users_dal)]


def get_users_service(session: SessionDep, users_dal: UsersDALDep) -> UsersService:
    return UsersService(session, users_dal)


UsersServiceDep = Annotated[UsersService, Depends(get_users_service)]


def get_otp_service() -> OtpService:
    return build_otp_service()


OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]


def get_auth_service(
    otp_service: OtpServiceDep, users_service: UsersServiceDep
) -> AuthService:
    return AuthService(otp_service, users_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/otp/verify", auto_error=True)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users_dal: UsersDALDep,
) -> User:
    user_id = decode_user_token(token, "access")
    user = await users_dal.get_by_id(user_id)
    if user is None:
        raise InvalidTokenError("user not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
registration_scheme = HTTPBearer(auto_error=True)


async def get_registration_phone(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(registration_scheme)],
    users_dal: UsersDALDep,
) -> str:
    phone = decode_registration_token(creds.credentials)  # raises on bad/expired/type
    if await users_dal.get_by_phone(phone) is not None:
        raise PhoneAlreadyExistsError(phone)
    return phone


RegistrationPhone = Annotated[str, Depends(get_registration_phone)]


def get_saved_locations_dal(session: SessionDep) -> SavedLocationsDAL:
    return SavedLocationsDAL(session)


SavedLocationsDALDep = Annotated[SavedLocationsDAL, Depends(get_saved_locations_dal)]


def get_saved_locations_service(
    session: SessionDep, saved_locations_dal: SavedLocationsDALDep
) -> SavedLocationsService:
    return SavedLocationsService(session, saved_locations_dal)


SavedLocationsServiceDep = Annotated[
    SavedLocationsService, Depends(get_saved_locations_service)
]


async def get_owned_saved_location(
    saved_location_id: uuid.UUID,
    user: CurrentUser,
    saved_locations_dal: SavedLocationsDALDep,
) -> SavedLocation:
    location = await saved_locations_dal.get_by_id(saved_location_id)
    # 404 (not 403) when it belongs to someone else, so we don't leak existence
    if location is None or location.user_id != user.user_id:
        raise NotFoundError("saved location not found")
    return location


OwnedSavedLocation = Annotated[SavedLocation, Depends(get_owned_saved_location)]


# ── devices ──────────────────────────────────────────────────────────────────
def get_devices_dal(session: SessionDep) -> DevicesDAL:
    return DevicesDAL(session)


DevicesDALDep = Annotated[DevicesDAL, Depends(get_devices_dal)]


def get_devices_service(
    session: SessionDep, devices_dal: DevicesDALDep
) -> DevicesService:
    return DevicesService(session, devices_dal)


DevicesServiceDep = Annotated[DevicesService, Depends(get_devices_service)]


# ── shipments ────────────────────────────────────────────────────────────────
def get_shipments_dal(session: SessionDep) -> ShipmentsDAL:
    return ShipmentsDAL(session)


ShipmentsDALDep = Annotated[ShipmentsDAL, Depends(get_shipments_dal)]


def get_bids_dal(session: SessionDep) -> BidsDAL:
    return BidsDAL(session)


BidsDALDep = Annotated[BidsDAL, Depends(get_bids_dal)]


def get_shipment_expiry_dispatcher() -> ShipmentExpiryDispatcher:
    return ShipmentExpiryDispatcher()


ShipmentExpiryDispatcherDep = Annotated[
    ShipmentExpiryDispatcher, Depends(get_shipment_expiry_dispatcher)
]


def get_shipments_service(
    session: SessionDep,
    shipments_dal: ShipmentsDALDep,
    bids_dal: BidsDALDep,
    expiry_dispatcher: ShipmentExpiryDispatcherDep,
) -> ShipmentsService:
    return ShipmentsService(session, shipments_dal, bids_dal, expiry_dispatcher)


ShipmentsServiceDep = Annotated[ShipmentsService, Depends(get_shipments_service)]


def get_current_captain(user: CurrentUser) -> User:
    """Authenticated user who is a captain (has a profile). 403 otherwise.
    capitan_profile is eager-loaded by UsersDAL, so is_captain is safe here."""
    if not user.is_captain:
        raise PermissionDeniedError("captain only")
    return user


CurrentCaptain = Annotated[User, Depends(get_current_captain)]


async def get_owned_shipment(
    shipment_id: uuid.UUID,
    user: CurrentUser,
    shipments_dal: ShipmentsDALDep,
) -> Shipment:
    """Sender-owned. 404 (not 403) when missing or someone else's — no existence
    leak. NB: this is the friendly-error layer; the accept/cancel atomic gates
    remain the race-proof boundary."""
    shipment = await shipments_dal.get_by_id(shipment_id)
    if shipment is None or shipment.sender_id != user.user_id:
        raise NotFoundError("shipment not found")
    return shipment


OwnedShipment = Annotated[Shipment, Depends(get_owned_shipment)]


async def get_viewable_shipment(
    shipment_id: uuid.UUID,
    user: CurrentUser,
    shipments_dal: ShipmentsDALDep,
) -> Shipment:
    """Visible to the sender, the assigned captain, or any captain while it's
    still open (pending) — captains need to load a request to make an offer.
    Open shipments are already fully visible via GET /shipments/open, so this
    exposes nothing new. 404 to anyone else."""
    shipment = await shipments_dal.get_by_id(shipment_id)
    if shipment is None:
        raise NotFoundError("shipment not found")
    is_party = user.user_id in (shipment.sender_id, shipment.capitan_id)
    is_browsable = user.is_captain and shipment.status == ShipmentStatus.PENDING
    if not (is_party or is_browsable):
        raise NotFoundError("shipment not found")
    return shipment


ViewableShipment = Annotated[Shipment, Depends(get_viewable_shipment)]
