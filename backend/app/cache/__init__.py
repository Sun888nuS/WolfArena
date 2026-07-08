"""Cache adapter package."""

from app.cache.redis_client import close_redis, get_redis_client

__all__ = ["close_redis", "get_redis_client"]
