from redis.asyncio import Redis

from app.config import settings

redis_client: Redis | None = None


async def init_redis() -> None:
    """Open the shared Redis connection at app startup."""
    global redis_client
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    """Close the shared Redis connection at app shutdown."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> Redis:
    """Accessor used by DALs/helpers. Raises if the lifespan never ran."""
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return redis_client
