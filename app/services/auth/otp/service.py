

import logging
import re
from datetime import UTC, datetime, timedelta

from app.cache.base import get_redis
from app.config import settings
from app.services.auth.otp import security
from app.services.auth.otp.dal import OtpChallengeDAL
from app.services.auth.otp.exceptions import (
    CooldownActive,
    DailyCapExceeded,
    InvalidOrExpiredCode,
    InvalidPhone,
    TooManyAttempts,
)
from app.services.auth.otp.rate_limit import OtpRateLimiter
from app.services.auth.otp.results import ChallengeCreated, VerifyResult

logger = logging.getLogger("wasel.otp")
_SAUDI_PHONE = re.compile(r"^9665\d{8}$")


def validate_saudi_phone(phone: str) -> str:
    phone = phone.strip()
    if not _SAUDI_PHONE.match(phone):
        raise InvalidPhone()
    return phone


class OtpService:
    def __init__(self, dal: OtpChallengeDAL, rate_limiter: OtpRateLimiter) -> None:
        self.dal = dal
        self.rate_limiter = rate_limiter

    async def request(self, phone: str) -> ChallengeCreated:
        phone = validate_saudi_phone(phone)

        # Locked out of verifying? Don't mint a code the phone can't use — reject
        # here instead of letting the client get a code that fails on verify.
        if self.rate_limiter.verify_cap_reached(
            await self.rate_limiter.verify_fail_count(phone)
        ):
            raise TooManyAttempts()

        # Check the cooldown window
        if not await self.rate_limiter.try_reserve_cooldown(phone):
            raise CooldownActive()

        count = await self.rate_limiter.incr_daily(phone)
        # Check the daily cap  
        if self.rate_limiter.daily_cap_reached(count):
            raise DailyCapExceeded()

        code = security.generate_code()
        challenge_id = await self.dal.create(
            phone=phone,
            code_hash=security.hash_code(code),
            ttl=settings.otp_ttl_seconds,
        )

        # Dev delivery: log the code. Swap for a real SmsGateway later — and
        logger.info("OTP for %s: %s (challenge %s)", phone, code, challenge_id)
        
        #TODO: Call SMS Gateway
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.otp_ttl_seconds)
        return ChallengeCreated(challenge_id=challenge_id, expires_at=expires_at)

    async def verify(self, challenge_id: str, code: str) -> VerifyResult:
        challenge = await self.dal.get(challenge_id)
        if challenge is None:  # missing or TTL-expired
            raise InvalidOrExpiredCode()

        phone = challenge.phone

        # Check Retries
        if self.rate_limiter.verify_cap_reached(await self.rate_limiter.verify_fail_count(phone)):
            raise TooManyAttempts()

        if challenge.attempts >= settings.otp_max_attempts:
            raise TooManyAttempts()

        if security.verify_code(code, challenge.code_hash):
            await self.dal.delete(challenge_id)  # single-use
            return VerifyResult(phone=phone)

        # Wrong OTP increment attempts and fail count, then check if we just hit the attempts cap
        attempts = await self.dal.incr_attempts(challenge_id)
        await self.rate_limiter.incr_verify_fail(phone)
        if attempts >= settings.otp_max_attempts:
            raise TooManyAttempts()
        raise InvalidOrExpiredCode()


def build_otp_service() -> OtpService:
    redis = get_redis()
    return OtpService(dal=OtpChallengeDAL(redis), rate_limiter=OtpRateLimiter(redis))
