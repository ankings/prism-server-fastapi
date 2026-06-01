from redis.asyncio import Redis, from_url
from app.config import settings

_redis_client: Redis | None = None


async def init_redis() -> None:
    global _redis_client
    client = from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        raise RuntimeError(f"Redis connection failed at startup: {exc}") from exc
    _redis_client = client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client
