"""Tests for Redis cache layer with graceful degradation."""

from unittest.mock import AsyncMock

from nss.cache import CacheLayer


async def test_get_set_round_trip() -> None:
    cache = CacheLayer()
    cache._available = True
    cache._client = AsyncMock()
    cache._client.get = AsyncMock(return_value='{"key": "value"}')
    cache._client.setex = AsyncMock()

    await cache.set("gateway", "test-id", {"key": "value"}, ttl_seconds=60)
    cache._client.setex.assert_called_once()

    result = await cache.get("gateway", "test-id")
    assert result == {"key": "value"}


async def test_cache_miss_returns_none() -> None:
    cache = CacheLayer()
    cache._available = True
    cache._client = AsyncMock()
    cache._client.get = AsyncMock(return_value=None)

    result = await cache.get("gateway", "nonexistent")
    assert result is None


async def test_graceful_degradation_unavailable() -> None:
    cache = CacheLayer()
    # Don't connect - _available is False by default
    result = await cache.get("gateway", "test")
    assert result is None
    # set should also not raise
    await cache.set("gateway", "test", {"data": 1})


async def test_invalidate() -> None:
    cache = CacheLayer()
    cache._available = True
    cache._client = AsyncMock()
    cache._client.delete = AsyncMock()

    await cache.invalidate("gateway", "test-id")
    cache._client.delete.assert_called_once()


async def test_graceful_degradation_on_error() -> None:
    cache = CacheLayer()
    cache._available = True
    cache._client = AsyncMock()
    cache._client.get = AsyncMock(side_effect=ConnectionError("Redis down"))

    # Should not raise, just return None
    result = await cache.get("gateway", "test")
    assert result is None
