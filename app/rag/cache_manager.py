#!/usr/bin/env python3
"""
Query Cache Manager for RAG System
Caches frequently asked questions to improve response time
"""
import time
from typing import Dict, Any, Optional, Tuple
from collections import OrderedDict
import logging
from app.rag.smart_cache_key import generate_smart_cache_key

logger = logging.getLogger(__name__)


class QueryCache:
    """Simple in-memory cache for query results"""

    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """
        Initialize cache

        Args:
            max_size: Maximum number of cached entries
            ttl: Time to live in seconds (default 1 hour)
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }

    def _generate_key(self, query: str, mode: str = None) -> str:
        """Generate smart cache key from query with normalization and synonym handling"""
        return generate_smart_cache_key(query, mode)

    def get(self, query: str, mode: str = None) -> Optional[Any]:
        """
        Get cached result for query

        Returns:
            Cached result if exists and not expired, None otherwise
        """
        key = self._generate_key(query, mode)

        if key in self.cache:
            result, timestamp = self.cache[key]

            # Check if expired
            if time.time() - timestamp > self.ttl:
                # Expired, remove it
                del self.cache[key]
                logger.debug(f"Cache expired for query: {query[:50]}...")
                self.stats["misses"] += 1
                return None

            # Move to end (LRU)
            self.cache.move_to_end(key)
            self.stats["hits"] += 1
            logger.info(f"✅ Cache HIT for query: {query[:50]}...")
            return result

        self.stats["misses"] += 1
        logger.debug(f"Cache MISS for query: {query[:50]}...")
        return None

    def set(self, query: str, result: Any, mode: str = None):
        """
        Cache query result

        Args:
            query: The query string
            result: The result to cache
            mode: Optional mode identifier
        """
        key = self._generate_key(query, mode)

        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size:
            evicted = self.cache.popitem(last=False)
            self.stats["evictions"] += 1
            logger.debug(f"Evicted oldest cache entry: {evicted[0]}")

        # Store with timestamp
        self.cache[key] = (result, time.time())
        logger.info(f"📝 Cached result for query: {query[:50]}...")

    def clear(self):
        """Clear all cached entries"""
        self.cache.clear()
        logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "evictions": self.stats["evictions"],
            "hit_rate": f"{hit_rate:.2%}"
        }


# Global cache instance
_cache_instance: Optional[QueryCache] = None


def get_cache() -> QueryCache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = QueryCache(
            max_size=100,  # Store up to 100 queries
            ttl=7200       # 2 hours TTL
        )
    return _cache_instance


def cache_query_result(query: str, result: Any, mode: str = None):
    """Helper function to cache a query result"""
    cache = get_cache()
    cache.set(query, result, mode)


def get_cached_result(query: str, mode: str = None) -> Optional[Any]:
    """Helper function to get cached result"""
    cache = get_cache()
    return cache.get(query, mode)


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    cache = get_cache()
    return cache.get_stats()


