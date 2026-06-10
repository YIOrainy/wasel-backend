from fastapi import APIRouter, status

from app.db.models import User
from app.entrypoints.api.deps import AuthServiceDep, RegistrationPhone
from app.services.auth.auth_service import SessionTokens
from app.schemas.auth import (
    AccessTokenOut,
    AuthenticatedOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    RefreshIn,
    RegisterIn,
    RegistrationRequiredOut,
    VerifyOut,
)
from app.schemas.users import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _authenticated(user: User, tokens: SessionTokens) -> AuthenticatedOut:

    return AuthenticatedOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/otp/request", response_model=OtpRequestOut)
async def otp_request(
    payload: OtpRequestIn, auth_service: AuthServiceDep
) -> OtpRequestOut:
    challenge = await auth_service.start_login(payload.phone)
    return OtpRequestOut(
        challenge_id=challenge.challenge_id, expires_at=challenge.expires_at
    )


@router.post("/otp/verify", response_model=VerifyOut)
async def otp_verify(
    payload: OtpVerifyIn, auth_service: AuthServiceDep
) -> AuthenticatedOut | RegistrationRequiredOut:
    outcome = await auth_service.verify_login(payload.challenge_id, payload.code)
    if outcome.user is not None:
        return _authenticated(outcome.user, auth_service.issue_session(outcome.user))
    # user is not registered, give him a registration token
    return RegistrationRequiredOut(
        registration_token=auth_service.issue_registration_token(outcome.phone)
    )


@router.post(
    "/register", response_model=AuthenticatedOut, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterIn, phone: RegistrationPhone, auth_service: AuthServiceDep
) -> AuthenticatedOut:
    user = await auth_service.register(phone, payload.name, payload.email)
    return _authenticated(user, auth_service.issue_session(user))


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(payload: RefreshIn, auth_service: AuthServiceDep) -> AccessTokenOut:
    access_token = await auth_service.refresh_access(payload.refresh_token)
    return AccessTokenOut(access_token=access_token)
