"""Comprehensive test suite for PersistentCache v2.0

테스트 항목:
1. WAL 모드 확인
2. UPSERT (통계 보존)
3. 슬라이딩/절대 TTL
4. JSON+zlib 직렬화
5. 크기 제한 LRU
6. 동시성 (멀티스레드)
7. invalidate
8. 만료 정리
"""

import concurrent.futures
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from app.rag.persistent_cache import (
    PersistentCache,
    _dumps,
    _loads,
    cache_query_result_persistent,
    get_cached_result_persistent,
    get_persistent_cache_stats,
)


class TestSerialization:
    """직렬화 테스트"""

    def test_dumps_loads_basic(self):
        """기본 직렬화/역직렬화"""
        data = {"query": "test", "results": [1, 2, 3]}
        blob = _dumps(data)
        assert isinstance(blob, bytes)

        restored = _loads(blob)
        assert restored == data

    def test_dumps_loads_no_compression(self):
        """압축 없이"""
        data = {"test": "data"}
        blob = _dumps(data, compress=False)
        restored = _loads(blob, compressed=False)
        assert restored == data

    def test_dumps_loads_complex(self):
        """복잡한 객체"""
        data = {
            "query": "뷰파인더 케이블 얼마?",
            "results": [
                {"doc": "doc1", "score": 0.95},
                {"doc": "doc2", "score": 0.87},
            ],
            "metadata": {"total": 2, "mode": "chat"},
        }
        blob = _dumps(data)
        restored = _loads(blob)
        assert restored == data


class TestPersistentCacheBasic:
    """기본 캐시 기능 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        """임시 DB 경로"""
        return str(tmp_path / "test_cache.db")

    def test_init(self, cache_db):
        """초기화"""
        cache = PersistentCache(db_path=cache_db, ttl=60)
        assert os.path.exists(cache_db)
        assert cache.ttl == 60
        assert cache.ttl_mode == "sliding"

    def test_set_get(self, cache_db):
        """기본 set/get"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        query = "test query"
        result = ["doc1", "doc2", "doc3"]

        cache.set(query, result)
        retrieved = cache.get(query)

        assert retrieved == result

    def test_get_miss(self, cache_db):
        """캐시 미스"""
        cache = PersistentCache(db_path=cache_db, ttl=60)
        result = cache.get("nonexistent query")
        assert result is None

    def test_mode_separation(self, cache_db):
        """모드별 분리"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        query = "same query"
        cache.set(query, ["chat_result"], mode="chat")
        cache.set(query, ["doc_result"], mode="doc_anchored")

        chat_result = cache.get(query, mode="chat")
        doc_result = cache.get(query, mode="doc_anchored")

        assert chat_result == ["chat_result"]
        assert doc_result == ["doc_result"]


class TestWALMode:
    """WAL 모드 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_wal.db")

    def test_wal_enabled(self, cache_db):
        """journal_mode 설정 확인 (WAL 또는 DELETE)"""
        _cache = PersistentCache(db_path=cache_db)

        # DB 연결해서 journal_mode 확인
        conn = sqlite3.connect(cache_db)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        conn.close()

        # WSL 환경에서는 WAL이 지원되지 않아 DELETE로 폴백될 수 있음
        assert mode.upper() in ("WAL", "DELETE")


class TestUpsert:
    """UPSERT (통계 보존) 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_upsert.db")

    def test_upsert_preserves_created_at(self, cache_db):
        """UPSERT 시 created_at 보존"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        query = "test query"

        # 첫 번째 삽입
        cache.set(query, ["v1"])
        time.sleep(0.1)

        # DB에서 created_at 가져오기
        conn = cache._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT created_at, access_count FROM query_cache WHERE query=?", (query,)
        )
        first_created, first_count = cur.fetchone()
        conn.close()

        # 두 번째 갱신
        time.sleep(0.1)
        cache.set(query, ["v2"])

        # created_at은 유지, access_count는 증가해야 함
        conn = cache._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT created_at, access_count FROM query_cache WHERE query=?", (query,)
        )
        second_created, second_count = cur.fetchone()
        conn.close()

        assert abs(first_created - second_created) < 0.01  # 거의 동일
        assert second_count == first_count + 1

    def test_upsert_increments_access_count(self, cache_db):
        """UPSERT 시 access_count 증가"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        query = "counter test"

        # 3번 set
        for i in range(3):
            cache.set(query, [f"v{i}"])

        # access_count 확인
        conn = cache._connect()
        cur = conn.cursor()
        cur.execute("SELECT access_count FROM query_cache WHERE query=?", (query,))
        count = cur.fetchone()[0]
        conn.close()

        assert count >= 3  # 최소 3 (set에서 증가)


class TestTTL:
    """TTL 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_ttl.db")

    def test_absolute_ttl_expires(self, cache_db):
        """절대 TTL 만료"""
        cache = PersistentCache(db_path=cache_db, ttl=1, ttl_mode="absolute")

        query = "expire test"
        cache.set(query, ["data"])

        # 즉시 조회 (성공)
        assert cache.get(query) == ["data"]

        # 1.5초 대기
        time.sleep(1.5)

        # 만료되어야 함
        assert cache.get(query) is None

    def test_sliding_ttl_extends(self, cache_db):
        """슬라이딩 TTL 연장"""
        cache = PersistentCache(db_path=cache_db, ttl=2, ttl_mode="sliding")

        query = "sliding test"
        cache.set(query, ["data"])

        # 1초 대기 후 조회 (TTL 갱신)
        time.sleep(1)
        assert cache.get(query) == ["data"]

        # 다시 1초 대기 후 조회 (아직 유효)
        time.sleep(1)
        assert cache.get(query) == ["data"]

        # 2초 이상 대기 (만료)
        time.sleep(2.5)
        assert cache.get(query) is None


class TestSizeLimit:
    """크기 제한 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_size.db")

    def test_size_limit_enforced(self, cache_db):
        """크기 제한 강제"""
        # 매우 작은 제한 (0.1MB)
        cache = PersistentCache(db_path=cache_db, ttl=3600, max_db_mb=0.1)

        # 큰 데이터 저장 (100개)
        for i in range(100):
            cache.set(f"query_{i}", ["x" * 10000])  # 각 ~10KB

        # 크기 확인
        size = cache._db_file_size_mb()
        # 0.1MB를 초과하지 않아야 함 (또는 약간의 오버헤드 허용)
        assert size < 0.2  # 여유 있게 0.2MB 미만


class TestConcurrency:
    """동시성 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_concurrent.db")

    def test_concurrent_set_get(self, cache_db):
        """동시 set/get"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        def worker(thread_id):
            for i in range(10):
                query = f"query_{thread_id}_{i}"
                cache.set(query, [f"result_{thread_id}_{i}"])
                result = cache.get(query)
                assert result == [f"result_{thread_id}_{i}"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, tid) for tid in range(8)]
            concurrent.futures.wait(futures)

        # 80개 저장되어야 함
        stats = cache.get_stats()
        assert stats["total_entries"] == 80


class TestInvalidate:
    """invalidate 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_invalidate.db")

    def test_invalidate_prefix(self, cache_db):
        """프리픽스 무효화"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        # 여러 쿼리 저장
        cache.set("user:alice:profile", ["alice_data"])
        cache.set("user:alice:posts", ["alice_posts"])
        cache.set("user:bob:profile", ["bob_data"])
        cache.set("product:123", ["product_data"])

        # user:alice 프리픽스 무효화
        # 키는 generate_smart_cache_key로 생성되므로, 실제로는 해시 값
        # 직접 DB 삽입으로 테스트
        conn = cache._connect()
        cur = conn.cursor()
        # 수동 삽입 (실제 키 사용)
        cur.execute(
            "INSERT INTO query_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("prefix:user:alice", "test", b"data", time.time(), time.time(), 1, 1),
        )
        cur.execute(
            "INSERT INTO query_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("prefix:user:bob", "test", b"data", time.time(), time.time(), 1, 1),
        )
        conn.close()

        # 무효화
        cache.invalidate("prefix:user:alice")

        # 확인
        conn = cache._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM query_cache WHERE cache_key LIKE 'prefix:user:alice%'")
        count = cur.fetchone()[0]
        conn.close()

        assert count == 0  # alice 삭제됨


class TestStats:
    """통계 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_stats.db")

    def test_get_stats(self, cache_db):
        """통계 조회"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        # 몇 개 캐시
        for i in range(5):
            cache.set(f"query_{i}", [f"result_{i}"])

        # 일부 조회 (access_count 증가)
        cache.get("query_0")
        cache.get("query_0")
        cache.get("query_1")

        stats = cache.get_stats()

        assert stats["total_entries"] == 5
        assert stats["total_accesses"] >= 8  # 5번 set + 3번 get
        assert stats["ttl_mode"] == "sliding"
        assert stats["ttl_seconds"] == 60
        assert len(stats["top_queries"]) > 0


class TestClear:
    """clear 테스트"""

    @pytest.fixture
    def cache_db(self, tmp_path):
        return str(tmp_path / "test_clear.db")

    def test_clear_all(self, cache_db):
        """모든 캐시 삭제"""
        cache = PersistentCache(db_path=cache_db, ttl=60)

        # 저장
        for i in range(10):
            cache.set(f"query_{i}", [f"result_{i}"])

        # 삭제
        cache.clear()

        # 확인
        stats = cache.get_stats()
        assert stats["total_entries"] == 0


if __name__ == "__main__":
    # 직접 실행 시 간단한 검증
    print("Running basic persistent cache tests...")

    # 임시 DB
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")

        # 기본 테스트
        cache = PersistentCache(db_path=db_path, ttl=60)
        cache.set("query1", ["doc1", "doc2"])
        result = cache.get("query1")
        print(f"✅ Basic set/get: {result}")

        # WAL 확인
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        conn.close()
        print(f"✅ WAL mode: {mode}")

        # 통계
        stats = cache.get_stats()
        print(f"✅ Stats: {stats}")

        # 슬라이딩 TTL
        cache2 = PersistentCache(
            db_path=os.path.join(tmpdir, "test2.db"), ttl=2, ttl_mode="sliding"
        )
        cache2.set("q1", ["data"])
        time.sleep(1)
        assert cache2.get("q1") == ["data"]
        time.sleep(1)
        assert cache2.get("q1") == ["data"]  # 아직 유효 (슬라이딩)
        print("✅ Sliding TTL works")

    print("\n✅ All basic tests passed!")
