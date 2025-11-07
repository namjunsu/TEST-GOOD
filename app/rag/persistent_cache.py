#!/usr/bin/env python3
"""
Persistent Query Cache using SQLite
Stores frequently asked questions permanently across server restarts
"""
import os
import time
import sqlite3
import hashlib
import json
import pickle
from typing import Dict, Any, Optional
from pathlib import Path
import logging
from app.rag.smart_cache_key import generate_smart_cache_key

logger = logging.getLogger(__name__)


class PersistentCache:
    """SQLite-based persistent cache for query results"""

    def __init__(self, db_path: str = "var/cache/query_cache.db", ttl: int = 7200):
        """
        Initialize persistent cache

        Args:
            db_path: Path to SQLite database file
            ttl: Time to live in seconds (default 2 hours)
        """
        self.db_path = db_path
        self.ttl = ttl

        # Create directory if needed
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

        # Clean expired entries on startup
        self._cleanup_expired()

    def _init_db(self):
        """Initialize SQLite database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                cache_key TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                result_data BLOB NOT NULL,
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                access_count INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accessed_at
            ON query_cache(accessed_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON query_cache(created_at)
        """)

        conn.commit()
        conn.close()

        logger.info(f"Persistent cache initialized: {self.db_path}")

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

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT result_data, created_at, access_count
            FROM query_cache
            WHERE cache_key = ?
        """, (key,))

        row = cursor.fetchone()

        if row:
            result_data, created_at, access_count = row

            # Check if expired
            if time.time() - created_at > self.ttl:
                # Expired, delete it
                cursor.execute("DELETE FROM query_cache WHERE cache_key = ?", (key,))
                conn.commit()
                conn.close()
                logger.debug(f"Cache expired for query: {query[:50]}...")
                return None

            # Update access time and count
            cursor.execute("""
                UPDATE query_cache
                SET accessed_at = ?, access_count = ?
                WHERE cache_key = ?
            """, (time.time(), access_count + 1, key))

            conn.commit()
            conn.close()

            # Deserialize result
            result = pickle.loads(result_data)
            logger.info(f"✅ Persistent Cache HIT for query: {query[:50]}... (accessed {access_count + 1} times)")
            return result

        conn.close()
        logger.debug(f"Persistent Cache MISS for query: {query[:50]}...")
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

        # Serialize result
        result_data = pickle.dumps(result)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = time.time()

        # Insert or replace
        cursor.execute("""
            INSERT OR REPLACE INTO query_cache
            (cache_key, query, result_data, created_at, accessed_at, access_count)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (key, query, result_data, now, now))

        conn.commit()
        conn.close()

        logger.info(f"💾 Cached to persistent storage: {query[:50]}...")

    def clear(self):
        """Clear all cached entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM query_cache")
        conn.commit()
        conn.close()
        logger.info("Persistent cache cleared")

    def _cleanup_expired(self):
        """Remove expired entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff = time.time() - self.ttl
        cursor.execute("DELETE FROM query_cache WHERE created_at < ?", (cutoff,))
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total entries
        cursor.execute("SELECT COUNT(*) FROM query_cache")
        total_count = cursor.fetchone()[0]

        # Most accessed
        cursor.execute("""
            SELECT query, access_count
            FROM query_cache
            ORDER BY access_count DESC
            LIMIT 5
        """)
        top_queries = cursor.fetchall()

        # Total access count
        cursor.execute("SELECT SUM(access_count) FROM query_cache")
        total_accesses = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_entries": total_count,
            "total_accesses": total_accesses,
            "avg_accesses": total_accesses / total_count if total_count > 0 else 0,
            "top_queries": [{"query": q[:50], "count": c} for q, c in top_queries],
            "db_size_mb": os.path.getsize(self.db_path) / (1024 * 1024) if os.path.exists(self.db_path) else 0
        }


# Global cache instance
_persistent_cache_instance: Optional[PersistentCache] = None


def get_persistent_cache() -> PersistentCache:
    """Get or create global persistent cache instance"""
    global _persistent_cache_instance
    if _persistent_cache_instance is None:
        _persistent_cache_instance = PersistentCache(
            db_path="var/cache/query_cache.db",
            ttl=7200  # 2 hours
        )
    return _persistent_cache_instance


def cache_query_result_persistent(query: str, result: Any, mode: str = None):
    """Helper function to cache a query result persistently"""
    cache = get_persistent_cache()
    cache.set(query, result, mode)


def get_cached_result_persistent(query: str, mode: str = None) -> Optional[Any]:
    """Helper function to get persistently cached result"""
    cache = get_persistent_cache()
    return cache.get(query, mode)


def get_persistent_cache_stats() -> Dict[str, Any]:
    """Get persistent cache statistics"""
    cache = get_persistent_cache()
    return cache.get_stats()