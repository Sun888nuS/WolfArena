"""Redis client lifecycle helpers."""

from redis.asyncio import Redis

from app.config import get_settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the shared Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
