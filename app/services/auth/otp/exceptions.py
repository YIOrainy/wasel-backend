"""OTP domain errors. Framework-free on purpose — the HTTP layer (web pass)
catches these and maps them to status codes + a single generic client message
(docs/OTP.md §7), so nothing here imports FastAPI."""


class OtpError(Exception):
    """Base for every OTP domain error."""


class InvalidPhone(OtpError):
    """Phone failed the defensive format check (request-side)."""


class CooldownActive(OtpError):
    """A code was requested again before the cooldown window elapsed."""


class DailyCapExceeded(OtpError):
    """This phone has requested too many codes today."""


class InvalidOrExpiredCode(OtpError):
    """Generic verify failure — missing, expired, or wrong code. Deliberately
    indistinct so the client can't tell the failure modes apart."""


class TooManyAttempts(OtpError):
    """Attempt cap reached — per-challenge or per-phone."""
