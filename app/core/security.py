"""JWT issuance + decoding. Mirrors unicorn's core/security.py, minus password
hashing (auth here is OTP-based). Three token types:

  access       sub=user_id   short-lived  → API calls
  refresh      sub=user_id   long-lived   → mint new access (stateless)
  registration sub=phone     ~10 min      → authorize POST /auth/register only
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from jwt import ExpiredSignatureError, PyJWTError
from jwt import decode as jwt_decode
from jwt import encode as jwt_encode

from app.config import settings
from app.core.exceptions import (
    InvalidTokenError,
    InvalidTokenTypeError,
    TokenExpiredError,
)

ALGORITHM = "HS256"

UserTokenType = Literal["access", "refresh"]


def _encode(subject: str, token_type: str, expires_in: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "type": token_type,
    }
    return jwt_encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def encode_access_token(user_id: uuid.UUID) -> str:
    return _encode(str(user_id), "access", timedelta(minutes=settings.access_token_minutes))


def encode_refresh_token(user_id: uuid.UUID) -> str:
    return _encode(str(user_id), "refresh", timedelta(days=settings.refresh_token_days))


def encode_registration_token(phone: str) -> str:
    return _encode(
        phone, "registration", timedelta(minutes=settings.registration_token_minutes)
    )


def _decode(token: str, expected_type: str) -> str:
    """Validate signature/expiry/type, return the `sub` claim."""
    try:
        payload: dict[str, object] = jwt_decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM]
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("token expired") from exc
    except PyJWTError as exc:
        raise InvalidTokenError("invalid token") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenTypeError("invalid token type")
    return str(payload["sub"])


def decode_user_token(token: str, expected_type: UserTokenType) -> uuid.UUID:
    """For access/refresh tokens → the user id."""
    return uuid.UUID(_decode(token, expected_type))


def decode_registration_token(token: str) -> str:
    """For the registration token → the proven phone."""
    return _decode(token, "registration")
