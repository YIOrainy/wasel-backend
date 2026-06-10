from app.cache.base import get_redis


async def get_cache(key: str) -> str | None:
    return await get_redis().get(key)


async def set_cache(key: str, value: str, ttl: int = 300) -> None:
    await get_redis().set(key, value, ex=ttl)


async def delete_cache(key: str) -> None:
    await get_redis().delete(key)
