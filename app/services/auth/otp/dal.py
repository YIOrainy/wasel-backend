import uuid
from dataclasses import dataclass

from redis.asyncio import Redis

_KEY = "otp:chal:{challenge_id}"


@dataclass(frozen=True, slots=True)
class OtpChallenge:
    phone: str
    code_hash: str
    attempts: int


class OtpChallengeDAL:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(challenge_id: str) -> str:
        return _KEY.format(challenge_id=challenge_id)

    async def create(self, *, phone: str, code_hash: str, ttl: int) -> str:
        challenge_id = str(uuid.uuid4())
        key = self._key(challenge_id)
        pipe = self.redis.pipeline(transaction=True)
        pipe.hset(key, mapping={"phone": phone, "code_hash": code_hash, "attempts": 0})
        pipe.expire(key, ttl)
        await pipe.execute()
        return challenge_id

    async def get(self, challenge_id: str) -> OtpChallenge | None:
        data = await self.redis.hgetall(self._key(challenge_id))
        if not data:  # missing or TTL-expired
            return None
        return OtpChallenge(
            phone=data["phone"],
            code_hash=data["code_hash"],
            attempts=int(data["attempts"]),
        )

    async def incr_attempts(self, challenge_id: str) -> int:
        return await self.redis.hincrby(self._key(challenge_id), "attempts", 1)

    async def delete(self, challenge_id: str) -> None:
        await self.redis.delete(self._key(challenge_id))
