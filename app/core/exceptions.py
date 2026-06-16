"""Service-layer errors, translated to HTTP at the route boundary (see
core/error_handlers.py). Mirrors unicorn's pattern. OTP domain errors live
separately in services/auth/otp/exceptions.py and are mapped alongside these."""


class ServiceError(Exception):
    """Base for service-layer errors."""


class NotFoundError(ServiceError):
    """Resource does not exist or is not visible to the caller."""


class PhoneAlreadyExistsError(ServiceError):
    """A user with this phone is already registered (lost the create race)."""


class DuplicateLocationError(ServiceError):
    """User already has a saved location at these exact coordinates."""


class ShipmentNotAcceptableError(ServiceError):
    """Shipment is no longer accepting this action — already accepted, expired,
    cancelled, or past the pending/open window. The caller lost the race."""


class PermissionDeniedError(ServiceError):
    """Authenticated, but not allowed to perform this action (e.g. not a captain,
    not an admin)."""


class AuthError(ServiceError):
    """Base for authentication/authorization failures."""


class TokenExpiredError(AuthError):
    """JWT has passed its expiry."""


class InvalidTokenError(AuthError):
    """JWT signature is bad, malformed, or references a missing user."""


class InvalidTokenTypeError(AuthError):
    """Token `type` claim does not match the expected type."""
