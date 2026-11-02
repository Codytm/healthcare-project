"""JSON cache for the aggregate mortality queries.

A Redis failure on get or set is logged and ignored, so the route still runs SQL.
cache_clear is the exception: it raises, and the admin route turns that into a 503.
"""

import json
import logging
import os
from typing import Any

import redis

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300
_KEY_PREFIX = "healthtrack:"
_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.Redis.from_url(
            url,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
    return _client


def make_cache_key(route: str, params: dict) -> str:
    """Same route and filters always produce the same key. Null filters are omitted."""
    parts = [route]
    for name in sorted(params):
        value = params[name]
        if value is not None:
            parts.append(f"{name}={value}")
    return _KEY_PREFIX + ":".join(parts)


def cache_get(key: str) -> Any | None:
    try:
        raw = _redis().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Redis get failed for %s", key, exc_info=True)
        return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    try:
        _redis().setex(key, ttl, json.dumps(value))
    except Exception:
        logger.warning("Redis set failed for %s", key, exc_info=True)


def cache_clear() -> int:
    client = _redis()
    keys = list(client.scan_iter(match=f"{_KEY_PREFIX}*"))
    if not keys:
        return 0
    return int(client.delete(*keys))


def check_redis() -> bool:
    try:
        return bool(_redis().ping())
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)
        return False
