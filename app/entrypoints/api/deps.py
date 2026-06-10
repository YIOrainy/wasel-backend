
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTokenError, PhoneAlreadyExistsError
from app.core.security import decode_registration_token, decode_user_token
from app.db.base import AsyncSessionLocal
from app.db.models import User
from app.services.auth.auth_service import AuthService
from app.services.auth.otp.service import OtpService, build_otp_service
from app.services.users.dal import UsersDAL
from app.services.users.service import UsersService


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


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
