from dataclasses import dataclass

from app.core.exceptions import InvalidTokenError, PhoneAlreadyExistsError
from app.core.security import (
    decode_user_token,
    encode_access_token,
    encode_refresh_token,
    encode_registration_token,
)
from app.db.models import User
from app.services.auth.otp.results import ChallengeCreated
from app.services.auth.otp.service import OtpService
from app.services.users.service import UsersService


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    phone: str
    user: User | None

    @property
    def is_registered(self) -> bool:
        return self.user is not None


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, otp_service: OtpService, users_service: UsersService) -> None:
        self.otp_service = otp_service
        self.users_service = users_service

    async def start_login(self, phone: str) -> ChallengeCreated:
        return await self.otp_service.request(phone)

    async def verify_login(self, challenge_id: str, code: str) -> LoginOutcome:
        result = await self.otp_service.verify(challenge_id, code)  # raises on bad code
        user = await self.users_service.get_by_phone(result.phone)
        return LoginOutcome(phone=result.phone, user=user)

    async def register(self, phone: str, name: str, email: str | None) -> User:
        if await self.users_service.get_by_phone(phone) is not None:
            raise PhoneAlreadyExistsError(phone)
        return await self.users_service.create_user(name=name, phone=phone, email=email)

    async def refresh_access(self, refresh_token: str) -> str:
        user_id = decode_user_token(refresh_token, "refresh")
        if await self.users_service.get_by_id(user_id) is None:
            raise InvalidTokenError("user not found")
        return encode_access_token(user_id)

    def issue_session(self, user: User) -> SessionTokens:
        return SessionTokens(
            access_token=encode_access_token(user.user_id),
            refresh_token=encode_refresh_token(user.user_id),
        )

    def issue_registration_token(self, phone: str) -> str:
        return encode_registration_token(phone)
