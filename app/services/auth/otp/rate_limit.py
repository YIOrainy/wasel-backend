"""Per-phone anti-abuse counters (docs/OTP.md §8). All keyed on phone → pure
Redis. Per-IP limits are deferred to the web pass (they need the request IP).

otp:cooldown:{phone}        60s between sends            (SET NX EX)
otp:send:{phone}:{YYYYMMDD} daily send cap              (INCR + EXPIRE 1d)
otp:vfail:{phone}           cross-challenge verify cap  (INCR + EXPIRE window)
"""

from datetime import UTC, datetime

from redis.asyncio import Redis

from app.config import settings

_DAY_SECONDS = 86_400


class OtpRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def try_reserve_cooldown(self, phone: str) -> bool:
        was_set = await self.redis.set(
            f"otp:cooldown:{phone}", "1", nx=True, ex=settings.otp_cooldown_seconds
        )
        return bool(was_set)

    async def incr_daily(self, phone: str) -> int:
        day = datetime.now(UTC).strftime("%Y%m%d")
        key = f"otp:send:{phone}:{day}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, _DAY_SECONDS)
        return count

    def daily_cap_reached(self, count: int) -> bool:
        return count > settings.otp_daily_cap

    async def verify_fail_count(self, phone: str) -> int:
        val = await self.redis.get(f"otp:vfail:{phone}")
        return int(val) if val else 0

    def verify_cap_reached(self, count: int) -> bool:
        return count >= settings.otp_verify_fail_cap

    async def incr_verify_fail(self, phone: str) -> int:
        key = f"otp:vfail:{phone}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, settings.otp_verify_fail_window_seconds)
        return count
