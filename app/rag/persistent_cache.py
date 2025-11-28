#!/usr/bin/env python3
"""Persistent Query Cache v2.0 using SQLite

2025-11-11 v2.0 개선사항:
- WAL 모드: 멀티스레드 동시성 대폭 향상
- UPSERT: 통계/타임스탬프 보존 (INSERT OR REPLACE 대신)
- JSON+zlib 직렬화: pickle 보안 취약점 제거
- 슬라이딩 TTL: 자주 사용되는 캐시 유지
- 크기 기반 LRU: 디스크 풀림 방지
- 확률적 정리: 대량 트래픽에서 오버헤드 감소
- 연결 헬퍼: PRAGMA 일괄 적용
"""
import json
import logging
import os
import random
import sqlite3
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from app.rag.smart_cache_key import generate_smart_cache_key

logger = logging.getLogger(__name__)


# ---- 안전 직렬화 (JSON + zlib, pickle 미사용) --------------------------------


def _dumps(obj: Any, compress: bool = True) -> bytes:
    """JSON 직렬화 + 선택적 압축

    Args:
        obj: 직렬화할 객체
        compress: zlib 압축 여부

    Returns:
        직렬화된 바이트
    """
    data = json.dumps(
        {"v": 1, "payload": obj}, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return zlib.compress(data, level=6) if compress else data


def _loads(data: bytes, compressed: bool = True) -> Any:
    """JSON 역직렬화 + 선택적 압축 해제

    Args:
        data: 직렬화된 바이트
        compressed: zlib 압축 여부

    Returns:
        역직렬화된 객체

    Raises:
        ValueError: 스키마 버전 불일치
    """
    raw = zlib.decompress(data) if compressed else data
    obj = json.loads(raw.decode("utf-8"))
    if obj.get("v") != 1:
        raise ValueError("Unsupported schema version")
    return obj["payload"]


# ---- 메인 캐시 클래스 ---------------------------------------------------------


class PersistentCache:
    """SQLite-based persistent cache v2.0

    - WAL 저널 모드
    - UPSERT로 통계 보존
    - 슬라이딩/절대 TTL
    - 크기 제한 + LRU 축출
    """

    def __init__(
        self,
        db_path: str = "var/cache/query_cache.db",
        ttl: int = 7200,
        ttl_mode: str = "sliding",  # "absolute" | "sliding"
        max_db_mb: int = 256,  # 파일 상한 (MB)
        cleanup_prob: float = 0.01,  # set() 호출 시 확률적 정리
        compress: bool = True,
        key_func: Optional[Callable[[str, Optional[str]], str]] = None,
    ):
        """Initialize persistent cache

        Args:
            db_path: SQLite DB 파일 경로
            ttl: TTL (초, 기본 2시간)
            ttl_mode: "absolute" (생성 기준) 또는 "sliding" (마지막 접근 기준)
            max_db_mb: DB 파일 최대 크기 (MB)
            cleanup_prob: set() 호출 시 정리 확률 (0.0~1.0)
            compress: zlib 압축 여부
            key_func: 커스텀 키 생성 함수 (기본: generate_smart_cache_key)
        """
        self.db_path = db_path
        self.ttl = ttl
        self.ttl_mode = ttl_mode
        self.max_db_mb = max_db_mb
        self.cleanup_prob = cleanup_prob
        self.compress = compress
        self._generate_key = key_func or (
            lambda q, m=None: generate_smart_cache_key(q, m)
        )

        # 디렉토리 생성
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 초기화
        self._init_db()
        self._cleanup_expired()
        self._enforce_size_limit()

    # ---- SQLite 헬퍼 ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """SQLite 연결 생성 (PRAGMA 적용)

        Returns:
            설정된 SQLite 연결
        """
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA mmap_size=268435456;")  # 256MB
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        """데이터베이스 스키마 초기화"""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS query_cache (
                    cache_key   TEXT PRIMARY KEY,
                    query       TEXT NOT NULL,
                    result_data BLOB NOT NULL,
                    created_at  REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 1,
                    compressed  INTEGER NOT NULL DEFAULT 1
                )
            """)
            # 인덱스
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_accessed_at ON query_cache(accessed_at)",
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON query_cache(created_at)",
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_access_count ON query_cache(access_count)",
            )
            logger.info(f"Persistent cache v2.0 initialized: {self.db_path}")

    # ---- 핵심 API --------------------------------------------------------------

    def get(self, query: str, mode: str | None = None) -> Optional[Any]:
        """캐시된 결과 조회

        Args:
            query: 검색 질의
            mode: 검색 모드

        Returns:
            캐시된 결과 (없거나 만료 시 None)
        """
        key = self._generate_key(query, mode)
        now = time.time()

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT result_data, created_at, accessed_at, access_count, compressed
                FROM query_cache WHERE cache_key=?
            """,
                (key,),
            )
            row = cur.fetchone()

            if not row:
                logger.debug(f"Persistent Cache MISS for query: {query[:50]}...")
                return None

            result_data, created_at, accessed_at, access_count, compressed = row

            # TTL 체크
            expired_ref = (
                created_at if self.ttl_mode == "absolute" else max(created_at, accessed_at)
            )
            if now - expired_ref > self.ttl:
                cur.execute("DELETE FROM query_cache WHERE cache_key=?", (key,))
                logger.debug(f"Cache expired (deleted): {query[:50]}...")
                return None

            # 접근 시간/카운트 갱신
            cur.execute(
                """
                UPDATE query_cache
                SET accessed_at=?, access_count=access_count+1
                WHERE cache_key=?
            """,
                (now, key),
            )

        # 역직렬화
        try:
            result = _loads(result_data, compressed=bool(compressed))
        except Exception as e:
            logger.warning(f"Deserialization failed, evicting key={key}: {e}")
            with self._connect() as conn:
                conn.execute("DELETE FROM query_cache WHERE cache_key=?", (key,))
            return None

        logger.info(
            f"✅ Persistent Cache HIT: {query[:50]}... (accessed {access_count + 1} times)",
        )
        return result

    def set(self, query: str, result: Any, mode: str | None = None) -> None:
        """결과 캐싱

        Args:
            query: 검색 질의
            result: 캐시할 결과
            mode: 검색 모드
        """
        key = self._generate_key(query, mode)
        now = time.time()
        blob = _dumps(result, compress=self.compress)

        with self._connect() as conn:
            cur = conn.cursor()
            # UPSERT: created_at 유지, 나머지 갱신
            cur.execute(
                """
                INSERT INTO query_cache (cache_key, query, result_data, created_at, accessed_at, access_count, compressed)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    query=excluded.query,
                    result_data=excluded.result_data,
                    accessed_at=excluded.accessed_at,
                    access_count=query_cache.access_count+1,
                    compressed=excluded.compressed,
                    created_at=CASE
                        WHEN query_cache.created_at IS NULL THEN excluded.created_at
                        ELSE query_cache.created_at
                    END
            """,
                (key, query, blob, now, now, 1 if self.compress else 0),
            )

        # 확률적 정리
        if random.random() < self.cleanup_prob:
            self._cleanup_expired()
            self._enforce_size_limit()

        logger.info(f"💾 Persistent cache set: {query[:50]}...")

    # ---- 유지보수 --------------------------------------------------------------

    def clear(self) -> None:
        """모든 캐시 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM query_cache")
        logger.info("Persistent cache cleared")

    def _cleanup_expired(self) -> None:
        """만료 항목 제거"""
        now = time.time()
        ref_col = "created_at" if self.ttl_mode == "absolute" else "MAX(created_at, accessed_at)"

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM query_cache WHERE (? - {ref_col}) > ?", (now, self.ttl),
            )
            deleted = cur.rowcount or 0

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired cache entries")

    def _db_file_size_mb(self) -> float:
        """DB 파일 크기 (MB)

        Returns:
            파일 크기 (MB)
        """
        if not Path(self.db_path).exists():
            return 0.0
        return os.path.getsize(self.db_path) / (1024 * 1024)

    def _enforce_size_limit(self) -> None:
        """크기 제한 강제 (LRU 축출)"""
        size = self._db_file_size_mb()
        if size <= self.max_db_mb:
            return

        # 10% 여유 확보를 위해 LRU 축출

        with self._connect() as conn:
            cur = conn.cursor()
            # 오래된 것부터 제거
            cur.execute(
                """
                SELECT cache_key FROM query_cache
                ORDER BY accessed_at ASC LIMIT 1000
            """,
            )
            keys = [k for (k,) in cur.fetchall()]
            if keys:
                cur.executemany(
                    "DELETE FROM query_cache WHERE cache_key=?", [(k,) for k in keys],
                )
                logger.info(
                    f"Size limit exceeded ({size:.1f}MB). Evicted {len(keys)} entries",
                )

    # ---- 통계 & 유틸리티 -------------------------------------------------------

    def invalidate(self, prefix: str) -> None:
        """프리픽스로 캐시 무효화

        Args:
            prefix: 캐시 키 접두사
        """
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM query_cache WHERE cache_key LIKE ?", (f"{prefix}%",))
            deleted = cur.rowcount or 0
        logger.info(f"Invalidated {deleted} keys with prefix={prefix}")

    def get_stats(self) -> dict[str, Any]:
        """캐시 통계

        Returns:
            통계 딕셔너리
        """
        with self._connect() as conn:
            cur = conn.cursor()

            # 전체 카운트/접근 수
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(access_count),0) FROM query_cache",
            )
            total_count, total_accesses = cur.fetchone()

            # 상위 쿼리
            cur.execute(
                """
                SELECT query, access_count FROM query_cache
                ORDER BY access_count DESC LIMIT 5
            """,
            )
            top = [{"query": q[:80], "count": c} for q, c in cur.fetchall()]

        return {
            "total_entries": total_count or 0,
            "total_accesses": total_accesses or 0,
            "avg_accesses": (total_accesses / total_count) if total_count else 0,
            "top_queries": top,
            "db_size_mb": self._db_file_size_mb(),
            "ttl_mode": self.ttl_mode,
            "ttl_seconds": self.ttl,
        }


# ---- 전역 인스턴스 및 헬퍼 함수 -----------------------------------------------

_persistent_cache_instance: Optional[PersistentCache] = None


def get_persistent_cache() -> PersistentCache:
    """전역 persistent cache 인스턴스 반환 (싱글턴)

    Returns:
        PersistentCache 인스턴스
    """
    global _persistent_cache_instance
    if _persistent_cache_instance is None:
        _persistent_cache_instance = PersistentCache(
            db_path="var/cache/query_cache.db",
            ttl=7200,  # 2 hours
            ttl_mode="sliding",  # 슬라이딩 TTL 권장
            max_db_mb=256,
            cleanup_prob=0.01,
            compress=True,
        )
    return _persistent_cache_instance


def cache_query_result_persistent(query: str, result: Any, mode: str | None = None):
    """Helper function to cache a query result persistently

    Args:
        query: 검색 질의
        result: 캐시할 결과
        mode: 검색 모드
    """
    cache = get_persistent_cache()
    cache.set(query, result, mode)


def get_cached_result_persistent(query: str, mode: str | None = None) -> Optional[Any]:
    """Helper function to get persistently cached result

    Args:
        query: 검색 질의
        mode: 검색 모드

    Returns:
        캐시된 결과 (없으면 None)
    """
    cache = get_persistent_cache()
    return cache.get(query, mode)


def get_persistent_cache_stats() -> dict[str, Any]:
    """Get persistent cache statistics

    Returns:
        통계 딕셔너리
    """
    cache = get_persistent_cache()
    return cache.get_stats()
