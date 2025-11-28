#!/usr/bin/env python3
"""Query Cache Manager v2.0 for RAG System

2025-11-11 v2.0 개선사항:
- 스레드 안전성 (threading.RLock)
- 네임스페이스 키 (인덱스 버전/설정 반영)
- 캐시 스탬피드 방지 (in-flight de-dup)
- TTL 일관성 (set/get 양쪽 purge)
- monotonic clock 사용 (시계 변동 영향 제거)
- 관측성 개선 (hit_rate, inflight 통계)

Caches frequently asked questions to improve response time
"""
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from app.rag.smart_cache_key import generate_smart_cache_key

logger = logging.getLogger(__name__)


class QueryCache:
    """Thread-safe in-memory cache for query results with TTL and LRU eviction"""

    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """Initialize cache

        Args:
            max_size: Maximum number of cached entries
            ttl: Time to live in seconds (default 1 hour)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._lock = threading.RLock()
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expired": 0,
        }
        # 스탬피드 방지: 계산 중인 키 추적
        self._inflight: dict[str, threading.Event] = {}
        # monotonic clock (wall-clock 대신)
        self._monotonic = time.monotonic

    def _now(self) -> float:
        """현재 시간 (단조 시계)"""
        return self._monotonic()

    def _purge_expired(self) -> None:
        """만료된 항목 제거 (앞에서부터)"""
        now = self._now()
        expired_keys = []
        for k, (_, ts) in list(self.cache.items()):
            if now - ts > self.ttl:
                expired_keys.append(k)
            else:
                break  # OrderedDict는 삽입 순서 유지, TTL 지난 것만 제거

        for k in expired_keys:
            self.cache.pop(k, None)
            self.stats["expired"] += 1

        if expired_keys:
            logger.debug(f"Purged {len(expired_keys)} expired entries")

    def _generate_key(self, query: str, mode: Optional[str] = None,
                      namespace: Optional[str] = None) -> str:
        """Generate smart cache key with namespace

        Args:
            query: 검색 질의
            mode: 검색 모드 (chat, doc_anchored 등)
            namespace: 버전 네임스페이스 (index_ver|config_hash)

        Returns:
            네임스페이스 포함 캐시 키
        """
        base = generate_smart_cache_key(query, mode)
        return f"{namespace or 'default'}::{base}"

    def get(self, query: str, mode: Optional[str] = None,
            namespace: Optional[str] = None) -> Optional[Any]:
        """Get cached result for query (thread-safe)

        Args:
            query: 검색 질의
            mode: 검색 모드
            namespace: 버전 네임스페이스

        Returns:
            Cached result if exists and not expired, None otherwise
        """
        key = self._generate_key(query, mode, namespace)

        with self._lock:
            # 만료 항목 정리 (set/get 양쪽에서)
            self._purge_expired()

            item = self.cache.get(key)
            if item is None:
                self.stats["misses"] += 1
                logger.debug(f"Cache MISS: {key[:80]}...")
                return None

            result, ts = item

            # 재확인: 만료 여부
            if self._now() - ts > self.ttl:
                self.cache.pop(key, None)
                self.stats["misses"] += 1
                self.stats["expired"] += 1
                logger.debug(f"Cache EXPIRED: {key[:80]}...")
                return None

            # LRU 갱신
            self.cache.move_to_end(key)
            self.stats["hits"] += 1
            # HIT 로그는 debug로 (운영 로그량 제어)
            logger.debug(f"✅ Cache HIT: {key[:80]}...")
            return result

    def begin_inflight(self, query: str, mode: Optional[str] = None,
                       namespace: Optional[str] = None) -> bool:
        """캐시 스탬피드 방지: 계산 시작 신호

        Args:
            query: 검색 질의
            mode: 검색 모드
            namespace: 버전 네임스페이스

        Returns:
            True면 호출자가 계산 수행자(리더), False면 팔로워(대기)
        """
        key = self._generate_key(query, mode, namespace)
        with self._lock:
            if key in self._inflight:
                # 이미 다른 스레드가 계산 중
                return False
            # 새로운 이벤트 생성
            ev = threading.Event()
            self._inflight[key] = ev
            return True

    def end_inflight(self, query: str, mode: Optional[str] = None,
                     namespace: Optional[str] = None) -> None:
        """계산 완료 신호

        Args:
            query: 검색 질의
            mode: 검색 모드
            namespace: 버전 네임스페이스
        """
        key = self._generate_key(query, mode, namespace)
        with self._lock:
            ev = self._inflight.pop(key, None)
            if ev:
                ev.set()  # 대기 중인 스레드 깨우기

    def wait_inflight(self, query: str, mode: Optional[str] = None,
                      namespace: Optional[str] = None, timeout: float = 10.0) -> None:
        """다른 스레드의 계산 완료 대기

        Args:
            query: 검색 질의
            mode: 검색 모드
            namespace: 버전 네임스페이스
            timeout: 최대 대기 시간 (초)
        """
        key = self._generate_key(query, mode, namespace)
        with self._lock:
            ev = self._inflight.get(key)
        if ev:
            ev.wait(timeout=timeout)

    def set(self, query: str, result: Any, mode: Optional[str] = None,
            namespace: Optional[str] = None) -> None:
        """Cache query result (thread-safe)

        Args:
            query: 검색 질의
            result: 캐시할 결과
            mode: 검색 모드
            namespace: 버전 네임스페이스
        """
        key = self._generate_key(query, mode, namespace)

        with self._lock:
            # 만료 항목 정리
            self._purge_expired()

            # LRU 축출
            if len(self.cache) >= self.max_size:
                evicted = self.cache.popitem(last=False)
                self.stats["evictions"] += 1
                logger.debug(f"Evicted oldest: {evicted[0][:80]}...")

            # 저장
            self.cache[key] = (result, self._now())
            logger.debug(f"📝 Cached: {key[:80]}...")

    def clear(self) -> None:
        """Clear all cached entries (thread-safe)"""
        with self._lock:
            self.cache.clear()
            self._inflight.clear()
            logger.info("Cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics (thread-safe)"""
        with self._lock:
            total = self.stats["hits"] + self.stats["misses"]
            hit_rate = self.stats["hits"] / total if total > 0 else 0.0

            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "evictions": self.stats["evictions"],
                "expired": self.stats["expired"],
                "hit_rate": f"{hit_rate:.2%}",
                "inflight_count": len(self._inflight),
            }


# Global cache instance
_cache_instance: Optional[QueryCache] = None
_cache_lock = threading.Lock()


def get_cache() -> QueryCache:
    """Get or create global cache instance (thread-safe singleton)"""
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:  # Double-checked locking
                _cache_instance = QueryCache(
                    max_size=100,  # Store up to 100 queries
                    ttl=7200,       # 2 hours TTL
                )
    return _cache_instance


def cache_query_result(query: str, result: Any, mode: Optional[str] = None,
                       namespace: Optional[str] = None) -> None:
    """Helper function to cache a query result

    Args:
        query: 검색 질의
        result: 캐시할 결과
        mode: 검색 모드
        namespace: 버전 네임스페이스
    """
    cache = get_cache()
    cache.set(query, result, mode, namespace)


def get_cached_result(query: str, mode: Optional[str] = None,
                      namespace: Optional[str] = None) -> Optional[Any]:
    """Helper function to get cached result

    Args:
        query: 검색 질의
        mode: 검색 모드
        namespace: 버전 네임스페이스

    Returns:
        Cached result or None
    """
    cache = get_cache()
    return cache.get(query, mode, namespace)


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics"""
    cache = get_cache()
    return cache.get_stats()


def build_answer_cache_key(query: str, selected_filename: Optional[str] = None) -> str:
    """answer() 메서드용 캐시 키 생성 (단일 소스)

    Args:
        query: 검색 질의
        selected_filename: 선택된 파일명 (있을 경우)

    Returns:
        캐시 키 문자열
    """
    return f"{query}:{selected_filename}" if selected_filename else query
