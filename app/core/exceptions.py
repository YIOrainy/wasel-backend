"""Service-layer errors, translated to HTTP at the route boundary (see
core/error_handlers.py). Mirrors unicorn's pattern. OTP domain errors live
separately in services/auth/otp/exceptions.py and are mapped alongside these."""


class ServiceError(Exception):
    """Base for service-layer errors."""


class NotFoundError(ServiceError):
    """Resource does not exist or is not visible to the caller."""


class PhoneAlreadyExistsError(ServiceError):
    """A user with this phone is already registered (lost the create race)."""


class AuthError(ServiceError):
    """Base for authentication/authorization failures."""


class TokenExpiredError(AuthError):
    """JWT has passed its expiry."""


class InvalidTokenError(AuthError):
    """JWT signature is bad, malformed, or references a missing user."""


class InvalidTokenTypeError(AuthError):
    """Token `type` claim does not match the expected type."""
