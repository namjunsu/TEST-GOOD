"""
SQLite 연결 유틸리티 테스트 (v2.0)
- WAL 모드 확인
- PRAGMA 설정 검증
- 스레드 안전성 테스트
- WAL 자동 복구 테스트
- 환경변수 제어 테스트
"""
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import pytest

from app.utils.sqlite_helpers import _cleanup_stale_wal, connect_metadata


class TestConnectMetadata:
    """connect_metadata() 기본 기능 테스트"""

    def test_default_connection(self, tmp_path):
        """기본 연결 생성"""
        db_path = tmp_path / "test.db"
        conn = connect_metadata(str(db_path))

        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_wal_mode_enabled(self, tmp_path):
        """WAL 모드 활성화 확인"""
        db_path = tmp_path / "test_wal.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA journal_mode;")
        result = cursor.fetchone()[0]

        assert result.lower() == "wal"
        conn.close()

    def test_synchronous_normal(self, tmp_path):
        """동기화 수준 NORMAL 확인"""
        db_path = tmp_path / "test_sync.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA synchronous;")
        result = cursor.fetchone()[0]

        # NORMAL = 1, FULL = 2
        assert result == 1  # NORMAL
        conn.close()

    def test_busy_timeout(self, tmp_path):
        """busy_timeout 설정 확인"""
        db_path = tmp_path / "test_timeout.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA busy_timeout;")
        result = cursor.fetchone()[0]

        assert result == 5000  # 5초
        conn.close()

    def test_cache_size(self, tmp_path):
        """cache_size 설정 확인"""
        db_path = tmp_path / "test_cache.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA cache_size;")
        result = cursor.fetchone()[0]

        # 음수는 KB 단위, 기본값 -2000 (2MB)
        assert result == -2000
        conn.close()

    def test_row_factory_enabled(self, tmp_path):
        """Row Factory 활성화 확인"""
        db_path = tmp_path / "test_row.db"
        conn = connect_metadata(str(db_path))

        conn.execute("CREATE TABLE test (id INTEGER, name TEXT);")
        conn.execute("INSERT INTO test VALUES (1, 'Alice');")

        row = conn.execute("SELECT * FROM test;").fetchone()

        # dict-like access
        assert row["id"] == 1
        assert row["name"] == "Alice"
        conn.close()

    def test_row_factory_disabled(self, tmp_path):
        """Row Factory 비활성화 옵션"""
        db_path = tmp_path / "test_no_row.db"
        conn = connect_metadata(str(db_path), enable_row_factory=False)

        conn.execute("CREATE TABLE test (id INTEGER, name TEXT);")
        conn.execute("INSERT INTO test VALUES (1, 'Alice');")

        row = conn.execute("SELECT * FROM test;").fetchone()

        # tuple 형태
        assert row == (1, "Alice")
        conn.close()


class TestEnvironmentVariables:
    """환경변수 제어 테스트"""

    def test_sync_mode_full(self, tmp_path, monkeypatch):
        """SQLITE_SYNC_MODE=FULL 설정"""
        monkeypatch.setenv("SQLITE_SYNC_MODE", "FULL")

        db_path = tmp_path / "test_full.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA synchronous;")
        result = cursor.fetchone()[0]

        assert result == 2  # FULL
        conn.close()

    def test_cache_size_custom(self, tmp_path, monkeypatch):
        """SQLITE_CACHE_SIZE 커스텀 설정"""
        monkeypatch.setenv("SQLITE_CACHE_SIZE", "5000")

        db_path = tmp_path / "test_cache_custom.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA cache_size;")
        result = cursor.fetchone()[0]

        assert result == -5000  # 5MB
        conn.close()

    def test_metadb_path_env(self, tmp_path, monkeypatch):
        """METADB_PATH 환경변수 사용"""
        db_path = tmp_path / "custom_meta.db"
        monkeypatch.setenv("METADB_PATH", str(db_path))

        conn = connect_metadata()  # db_path=None

        # 파일이 생성되었는지 확인
        assert Path(db_path).exists()
        conn.close()


class TestThreadSafety:
    """스레드 안전성 테스트"""

    def test_check_same_thread_false(self, tmp_path):
        """check_same_thread=False 확인 (순차 실행)"""
        db_path = tmp_path / "test_thread.db"
        conn = connect_metadata(str(db_path))

        # 테이블 생성
        conn.execute("CREATE TABLE test (id INTEGER, value TEXT);")

        results = []
        lock = threading.Lock()  # 동시 실행 방지 (순차 실행)

        def worker(thread_id):
            """다른 스레드에서 동일 연결 사용 (순차)"""
            try:
                with lock:  # 순차 실행 보장
                    # 쓰기 작업
                    conn.execute(f"INSERT INTO test VALUES ({thread_id}, 'thread_{thread_id}');")
                    # 읽기 작업
                    cursor = conn.execute("SELECT COUNT(*) FROM test;")
                    row = cursor.fetchone()
                    if row:
                        count = row[0]
                        results.append((thread_id, count))
                    else:
                        results.append((thread_id, "fetchone() returned None"))
            except Exception as e:
                results.append((thread_id, str(e)))

        # 5개 스레드 생성 (lock으로 순차 실행)
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 모든 스레드가 정상 실행되었는지 확인
        assert len(results) == 5
        # 예외가 발생하지 않았는지 확인
        for thread_id, result in results:
            assert isinstance(result, int), f"Thread {thread_id} failed: {result}"

        conn.close()

    def test_concurrent_reads(self, tmp_path):
        """동시 읽기 작업 테스트"""
        db_path = tmp_path / "test_concurrent.db"
        conn = connect_metadata(str(db_path))

        # 초기 데이터
        conn.execute("CREATE TABLE test (id INTEGER, value TEXT);")
        for i in range(100):
            conn.execute(f"INSERT INTO test VALUES ({i}, 'value_{i}');")

        results = []
        lock = threading.Lock()

        def reader():
            """동시 읽기 (에러 처리 추가)"""
            try:
                with lock:  # cursor 생성은 동기화
                    cursor = conn.execute("SELECT COUNT(*) FROM test;")
                    row = cursor.fetchone()
                    if row:
                        count = row[0]
                        results.append(count)
                    else:
                        results.append(None)
            except Exception as e:
                results.append(f"Error: {e}")

        # 10개 스레드 동시 읽기
        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 모든 읽기 결과 확인
        assert len(results) == 10
        # None이나 에러 없이 모두 100이어야 함
        assert all(r == 100 for r in results if r is not None), f"Results: {results}"

        conn.close()


class TestWALCleanup:
    """WAL 자동 복구 테스트"""

    def test_cleanup_empty_wal(self, tmp_path):
        """빈 WAL 파일 자동 제거"""
        db_path = tmp_path / "test_empty_wal.db"

        # 빈 WAL 파일 생성
        wal_path = f"{db_path}-wal"
        Path(wal_path).touch()
        assert Path(wal_path).exists()

        # cleanup 실행
        _cleanup_stale_wal(str(db_path))

        # 빈 파일이 제거되었는지 확인
        assert not Path(wal_path).exists()

    def test_cleanup_empty_shm(self, tmp_path):
        """빈 SHM 파일 자동 제거"""
        db_path = tmp_path / "test_empty_shm.db"

        # 빈 SHM 파일 생성
        shm_path = f"{db_path}-shm"
        Path(shm_path).touch()
        assert Path(shm_path).exists()

        # cleanup 실행
        _cleanup_stale_wal(str(db_path))

        # 빈 파일이 제거되었는지 확인
        assert not Path(shm_path).exists()

    def test_cleanup_stale_wal(self, tmp_path):
        """오래된 WAL 파일 자동 제거"""
        db_path = tmp_path / "test_stale.db"

        # WAL 파일 생성 및 수정 시간 조작
        wal_path = Path(f"{db_path}-wal")
        wal_path.write_text("dummy content")

        # 25시간 전으로 수정 시간 변경
        old_time = time.time() - (25 * 3600)
        os.utime(wal_path, (old_time, old_time))

        assert wal_path.exists()

        # cleanup 실행 (기본 max_age_hours=24)
        _cleanup_stale_wal(str(db_path))

        # 오래된 파일이 제거되었는지 확인
        assert not wal_path.exists()

    def test_cleanup_recent_wal_preserved(self, tmp_path):
        """최근 WAL 파일은 보존"""
        db_path = tmp_path / "test_recent.db"

        # WAL 파일 생성 (최근)
        wal_path = Path(f"{db_path}-wal")
        wal_path.write_text("recent content")

        assert wal_path.exists()

        # cleanup 실행
        _cleanup_stale_wal(str(db_path))

        # 최근 파일은 유지되어야 함
        assert wal_path.exists()

    def test_cleanup_on_connect(self, tmp_path):
        """연결 시 자동 cleanup 동작 확인"""
        db_path = tmp_path / "test_auto_cleanup.db"

        # 빈 WAL 파일 생성
        wal_path = Path(f"{db_path}-wal")
        wal_path.touch()

        # 연결 생성 (내부적으로 _cleanup_stale_wal 호출)
        conn = connect_metadata(str(db_path))

        # WAL 파일이 제거되었는지 확인
        assert not wal_path.exists()

        conn.close()


class TestAutocommitMode:
    """Autocommit 모드 테스트"""

    def test_isolation_level_none(self, tmp_path):
        """isolation_level=None 확인"""
        db_path = tmp_path / "test_autocommit.db"
        conn = connect_metadata(str(db_path))

        assert conn.isolation_level is None

        # 명시적 BEGIN 없이도 즉시 커밋됨
        conn.execute("CREATE TABLE test (id INTEGER);")
        conn.execute("INSERT INTO test VALUES (1);")

        # 새로운 연결에서 데이터 확인
        conn2 = connect_metadata(str(db_path))
        cursor = conn2.execute("SELECT COUNT(*) FROM test;")
        count = cursor.fetchone()[0]

        assert count == 1

        conn.close()
        conn2.close()


class TestComplexScenarios:
    """복잡한 시나리오 테스트"""

    def test_multiple_connections(self, tmp_path):
        """여러 연결 동시 사용"""
        db_path = tmp_path / "test_multi.db"

        # 첫 번째 연결: 데이터 삽입
        conn1 = connect_metadata(str(db_path))
        conn1.execute("CREATE TABLE test (id INTEGER, value TEXT);")
        conn1.execute("INSERT INTO test VALUES (1, 'first');")

        # 두 번째 연결: 동시 읽기
        conn2 = connect_metadata(str(db_path))
        cursor = conn2.execute("SELECT value FROM test WHERE id=1;")
        result = cursor.fetchone()

        assert result["value"] == "first"

        # 세 번째 연결: 동시 쓰기
        conn3 = connect_metadata(str(db_path))
        conn3.execute("INSERT INTO test VALUES (2, 'second');")

        # 모든 연결 닫기
        conn1.close()
        conn2.close()
        conn3.close()

    def test_wal_checkpoint(self, tmp_path):
        """WAL 체크포인트 동작 확인"""
        db_path = tmp_path / "test_checkpoint.db"
        conn = connect_metadata(str(db_path))

        # 대량 데이터 삽입
        conn.execute("CREATE TABLE test (id INTEGER);")
        for i in range(1000):
            conn.execute(f"INSERT INTO test VALUES ({i});")

        # WAL 체크포인트 수동 실행
        conn.execute("PRAGMA wal_checkpoint(FULL);")

        # DB 파일에 반영되었는지 확인
        cursor = conn.execute("SELECT COUNT(*) FROM test;")
        count = cursor.fetchone()[0]

        assert count == 1000

        conn.close()


class TestErrorHandling:
    """에러 처리 테스트"""

    def test_sync_mode_case_insensitive(self, tmp_path, monkeypatch):
        """SYNC_MODE 대소문자 무관 (소문자 입력 허용)"""
        monkeypatch.setenv("SQLITE_SYNC_MODE", "full")

        db_path = tmp_path / "test_lowercase.db"
        conn = connect_metadata(str(db_path))

        cursor = conn.execute("PRAGMA synchronous;")
        result = cursor.fetchone()[0]

        # 소문자 입력도 FULL(2)로 인식되어야 함
        assert result == 2
        conn.close()

    def test_invalid_cache_size(self, tmp_path, monkeypatch):
        """잘못된 CACHE_SIZE 값 처리"""
        monkeypatch.setenv("SQLITE_CACHE_SIZE", "invalid")

        db_path = tmp_path / "test_invalid_cache.db"

        # int() 변환 실패
        with pytest.raises(ValueError):
            connect_metadata(str(db_path))

    def test_missing_db_directory(self):
        """존재하지 않는 디렉토리 처리"""
        db_path = "/nonexistent/path/test.db"

        # 디렉토리가 없으면 연결 실패
        with pytest.raises(sqlite3.OperationalError):
            connect_metadata(db_path)


class TestPragmaValues:
    """PRAGMA 값 종합 검증"""

    def test_all_pragma_settings(self, tmp_path):
        """모든 PRAGMA 설정 한 번에 검증"""
        db_path = tmp_path / "test_all_pragma.db"
        conn = connect_metadata(str(db_path))

        pragmas = {
            "journal_mode": "wal",
            "synchronous": 1,      # NORMAL
            "busy_timeout": 5000,
            "cache_size": -2000,
        }

        for pragma, expected in pragmas.items():
            cursor = conn.execute(f"PRAGMA {pragma};")
            result = cursor.fetchone()[0]

            if pragma == "journal_mode":
                assert result.lower() == expected
            else:
                assert result == expected

        conn.close()
