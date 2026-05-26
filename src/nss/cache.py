"""Redis-based caching layer with graceful degradation.

If Redis is unavailable, the cache silently degrades to a no-op,
ensuring the system operates without interruption.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CacheLayer:
    """Async Redis cache wrapper with graceful degradation.

    Args:
        redis_url: Redis connection URL.
        key_prefix: Prefix for all cache keys.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", key_prefix: str = "nss") -> None:
        self._redis_url = redis_url
        self._prefix = key_prefix
        self._client: Any | None = None
        self._available = False

    async def connect(self) -> None:
        """Attempt to connect to Redis."""
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            # redis-py async client returns Awaitable[bool] | bool; cast to satisfy mypy.
            ping_result = self._client.ping()
            if hasattr(ping_result, "__await__"):
                await ping_result
            self._available = True
            logger.info("cache_connected", url=self._redis_url)
        except Exception:
            self._available = False
            self._client = None
            logger.warning("cache_unavailable", url=self._redis_url)

    def _make_key(self, layer: str, identifier: str) -> str:
        """Generate a cache key."""
        hash_val = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{self._prefix}:{layer}:{hash_val}"

    async def get(self, layer: str, identifier: str) -> Any | None:
        """Retrieve a cached value.

        Returns None on cache miss or if Redis is unavailable.
        """
        if not self._available or not self._client:
            return None
        try:
            key = self._make_key(layer, identifier)
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            logger.warning("cache_get_failed", layer=layer)
            return None

    async def set(
        self,
        layer: str,
        identifier: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        """Store a value in cache with TTL."""
        if not self._available or not self._client:
            return
        try:
            key = self._make_key(layer, identifier)
            await self._client.setex(key, ttl_seconds, json.dumps(value))
        except Exception:
            logger.warning("cache_set_failed", layer=layer)

    async def invalidate(self, layer: str, identifier: str) -> None:
        """Remove a specific cache entry."""
        if not self._available or not self._client:
            return
        try:
            key = self._make_key(layer, identifier)
            await self._client.delete(key)
        except Exception:
            logger.warning("cache_invalidate_failed", layer=layer)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._available = False
