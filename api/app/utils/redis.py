"""
Redis Connection & Caching Utilities
"""
import redis.asyncio as redis
from typing import Optional, Any
import json
import logging
from functools import wraps

from app.config import settings

logger = logging.getLogger(__name__)

# Redis client instance
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    logger.info("Initializing Redis connection...")
    redis_client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,  # 5 second connection timeout
        socket_timeout=5,  # 5 second operation timeout
        retry_on_timeout=True,
    )
    # Test connection
    try:
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Caching will be disabled.")


async def close_redis():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        logger.info("Closing Redis connection...")
        await redis_client.close()
        logger.info("Redis connection closed")


class NoOpCache:
    """A no-op cache that does nothing - used when Redis is unavailable"""
    async def get(self, key: str) -> None:
        return None
    
    async def set(self, key: str, value: Any, *args, **kwargs) -> bool:
        return True
    
    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        return True
    
    async def delete(self, key: str) -> int:
        return 0
    
    async def exists(self, key: str) -> int:
        return 0
    
    async def keys(self, pattern: str) -> list:
        return []

_noop_cache = NoOpCache()


async def get_redis() -> redis.Redis:
    """
    Dependency that provides Redis client
    Usage: cache: redis.Redis = Depends(get_redis)
    
    Returns a no-op cache if Redis is unavailable (graceful degradation)
    """
    if redis_client is None:
        logger.warning("Redis client not initialized, using no-op cache")
        return _noop_cache
    
    # Quick health check
    try:
        await redis_client.ping()
        return redis_client
    except Exception as e:
        logger.warning(f"Redis ping failed: {e}, using no-op cache")
        return _noop_cache


class CacheService:
    """
    High-level caching service with common patterns
    """
    
    def __init__(self, client: redis.Redis):
        self.client = client
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = await self.client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = settings.CACHE_TTL_DEFAULT
    ) -> bool:
        """Set value in cache with TTL"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return await self.client.setex(key, ttl, value)
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        return await self.client.delete(key) > 0
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        keys = await self.client.keys(pattern)
        if keys:
            return await self.client.delete(*keys)
        return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        return await self.client.exists(key) > 0
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        return await self.client.incrby(key, amount)
    
    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: int = settings.CACHE_TTL_DEFAULT
    ) -> Any:
        """Get from cache or compute and cache"""
        value = await self.get(key)
        if value is not None:
            return value
        
        # Compute value
        if callable(factory):
            value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        else:
            value = factory
        
        await self.set(key, value, ttl)
        return value


def cached(
    prefix: str,
    ttl: int = settings.CACHE_TTL_DEFAULT,
    key_builder: Optional[callable] = None
):
    """
    Decorator for caching async function results
    
    Usage:
        @cached("flights", ttl=300)
        async def search_flights(origin: str, destination: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                key_parts = [str(arg) for arg in args]
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{prefix}:{':'.join(key_parts)}"
            
            # Try cache
            cached_value = await redis_client.get(cache_key)
            if cached_value:
                logger.debug(f"Cache HIT: {cache_key}")
                return json.loads(cached_value)
            
            # Execute function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                await redis_client.setex(
                    cache_key, 
                    ttl, 
                    json.dumps(result, default=str)
                )
            
            return result
        return wrapper
    return decorator


import asyncio

