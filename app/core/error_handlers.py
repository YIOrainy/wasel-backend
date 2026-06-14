"""Map domain exceptions → HTTP responses at the route boundary. The OTP verify
failures collapse to one generic message (docs/OTP.md §7); request-side limits
get 429s; auth errors get 401s."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    DuplicateLocationError,
    InvalidTokenError,
    InvalidTokenTypeError,
    NotFoundError,
    PhoneAlreadyExistsError,
    TokenExpiredError,
)
from app.services.auth.otp.exceptions import (
    CooldownActive,
    DailyCapExceeded,
    InvalidOrExpiredCode,
    InvalidPhone,
    TooManyAttempts,
)

_BEARER = {"WWW-Authenticate": "Bearer"}


def _json(code: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail}, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    # ── OTP request-side ─────────────────────────────────────────────────────
    app.add_exception_handler(
        InvalidPhone,
        lambda r, e: _json(status.HTTP_400_BAD_REQUEST, "invalid phone number"),
    )
    app.add_exception_handler(
        CooldownActive,
        lambda r, e: _json(
            status.HTTP_429_TOO_MANY_REQUESTS, "please wait before requesting another code"
        ),
    )
    app.add_exception_handler(
        DailyCapExceeded,
        lambda r, e: _json(
            status.HTTP_429_TOO_MANY_REQUESTS, "daily code limit reached, try again tomorrow"
        ),
    )
    # ── OTP verify-side (generic / indistinct) ───────────────────────────────
    app.add_exception_handler(
        InvalidOrExpiredCode,
        lambda r, e: _json(status.HTTP_400_BAD_REQUEST, "invalid or expired code"),
    )
    app.add_exception_handler(
        TooManyAttempts,
        lambda r, e: _json(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts"),
    )
    # ── users / auth ─────────────────────────────────────────────────────────
    app.add_exception_handler(
        NotFoundError, lambda r, e: _json(status.HTTP_404_NOT_FOUND, "not found")
    )
    app.add_exception_handler(
        PhoneAlreadyExistsError,
        lambda r, e: _json(status.HTTP_409_CONFLICT, "phone already registered"),
    )
    app.add_exception_handler(
        DuplicateLocationError,
        lambda r, e: _json(
            status.HTTP_409_CONFLICT, "location already saved at these coordinates"
        ),
    )
    app.add_exception_handler(
        TokenExpiredError,
        lambda r, e: _json(status.HTTP_401_UNAUTHORIZED, "token expired", _BEARER),
    )
    app.add_exception_handler(
        InvalidTokenTypeError,
        lambda r, e: _json(
            status.HTTP_401_UNAUTHORIZED, "invalid or expired token", _BEARER
        ),
    )
    app.add_exception_handler(
        InvalidTokenError,
        lambda r, e: _json(
            status.HTTP_401_UNAUTHORIZED, "could not validate credentials", _BEARER
        ),
    )
    app.add_exception_handler(
        AuthError,
        lambda r, e: _json(
            status.HTTP_401_UNAUTHORIZED, "could not validate credentials", _BEARER
        ),
    )
