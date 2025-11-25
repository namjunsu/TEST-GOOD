#!/usr/bin/env python3
"""
SQLite 연결 유틸리티 v2.1
busy_timeout, WAL 모드, 트랜잭션 컨텍스트를 갖춘 공용 메타DB 커넥터

핵심:
1. check_same_thread=False: 멀티스레드 환경 지원 (단, 커넥션 공유 금지)
2. executescript: PRAGMA 일괄 설정으로 연결 오버헤드 감소
3. journal_mode=WAL: 동시성 개선 및 안정성 강화
4. foreign_keys=ON: 무결성 제약 조건 강제
5. metadata_txn: 트랜잭션 컨텍스트 매니저 (롤백 문제 방지)
"""
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def connect_metadata(
    db_path: Optional[str] = None,
    enable_row_factory: bool = True,
) -> sqlite3.Connection:
    """
    메타데이터 DB 연결 (경합 및 스레드 내성 강화)

    Args:
        db_path: DB 경로. None이면 환경변수 METADB_PATH 또는 기본값 var/metadata.db 사용
        enable_row_factory: True이면 sqlite3.Row 활성화 (dict-like access)

    Returns:
        sqlite3.Connection: WAL / busy_timeout / autocommit / thread-safe 설정 완료된 연결

    환경변수:
        METADB_PATH: DB 파일 경로 (기본: metadata.db)
        SQLITE_SYNC_MODE: 동기화 수준 (NORMAL|FULL, 기본: NORMAL)
        SQLITE_CACHE_SIZE: 캐시 크기 KB 단위 (기본: 2000 → 2MB)

    설정:
        - journal_mode: DB 파일 설정 유지 (강제 변경하지 않음)
        - autocommit: isolation_level=None
        - busy_timeout: 5초 (잠금 대기)
        - check_same_thread: False (멀티스레드 접근 허용)

    주의:
        동일 Connection 객체를 여러 스레드가 동시에 사용하는 것은 금지.
        thread-local storage나 connection pool 사용 권장.
    """
    path = db_path or os.getenv("METADB_PATH", "metadata.db")
    sync_mode = os.getenv("SQLITE_SYNC_MODE", "NORMAL").upper()
    cache_size = int(os.getenv("SQLITE_CACHE_SIZE", "2000"))

    # WAL 자동 복구: 비정상 종료로 인한 빈 WAL/SHM 파일 제거
    _cleanup_stale_wal(path)

    # 연결 생성 (멀티스레드 지원)
    conn = sqlite3.connect(
        path,
        timeout=5.0,
        isolation_level=None,      # autocommit 모드
        check_same_thread=False,   # 멀티스레드 접근 허용
    )

    # PRAGMA 일괄 설정 (성능 + 안정성 최적화)
    # WAL 모드: 동시성 개선 및 롤백 문제 방지
    # foreign_keys: 무결성 제약 조건 강제
    conn.executescript(f"""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = {sync_mode};
        PRAGMA busy_timeout = 5000;
        PRAGMA cache_size = -{cache_size};
        PRAGMA foreign_keys = ON;
    """)

    # Row Factory 설정 (dict-like access)
    if enable_row_factory:
        conn.row_factory = sqlite3.Row

    # Get current journal mode
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    logger.info(
        f"SQLite connected: {path}, journal_mode={journal_mode}, sync={sync_mode}, cache={cache_size}KB"
    )

    return conn


@contextmanager
def metadata_txn(mode: str = "IMMEDIATE", db_path: Optional[str] = None):
    """
    트랜잭션 컨텍스트 매니저 (문서 개수 롤백 문제 방지)

    Args:
        mode: 트랜잭션 모드
            - "IMMEDIATE": 쓰기 락 확보 (권장, 일반 쓰기 작업용)
            - "EXCLUSIVE": 독점 락 (대량 작업용, 재인덱싱 등)
            - "DEFERRED": 읽기 전용 또는 지연 락 (비권장)
        db_path: DB 경로 (None이면 기본값)

    Yields:
        sqlite3.Connection: 트랜잭션이 시작된 연결

    Example:
        ```python
        from app.utils.sqlite_helpers import metadata_txn

        # 일반 쓰기
        with metadata_txn(mode="IMMEDIATE") as conn:
            conn.execute("INSERT INTO documents (...) VALUES (...)")
            # 예외 발생 시 자동 rollback, 정상 시 commit

        # 대량 작업
        with metadata_txn(mode="EXCLUSIVE") as conn:
            for doc in docs:
                conn.execute("INSERT INTO documents (...) VALUES (...)", doc)
        ```

    Important:
        - autocommit 모드(isolation_level=None)에서는 수동 트랜잭션 필요
        - 예외 발생 시 자동 rollback
        - 정상 완료 시 자동 commit
    """
    conn = connect_metadata(db_path, enable_row_factory=False)
    try:
        conn.execute(f"BEGIN {mode}")
        yield conn
        conn.commit()
    except Exception as e:
        logger.error(f"metadata_txn rollback ({mode}): {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def _cleanup_stale_wal(db_path: str, max_age_hours: int = 24) -> None:
    """
    비정상 종료로 인한 빈 WAL/SHM 파일만 정리

    - 0 byte 파일 → 즉시 삭제
    - 그 외에는 절대 자동 삭제하지 않고 경고만 로그로 남김

    Args:
        db_path: DB 파일 경로
        max_age_hours: WAL 파일 경과 시간 (경고용, 삭제하지 않음)

    중요:
        데이터가 있는 WAL/SHM 파일은 절대 자동 삭제하지 않음
        자동 삭제 시 커밋된 변경사항이 유실될 수 있음
    """
    for suffix in ("-wal", "-shm"):
        wal_path = f"{db_path}{suffix}"

        if not os.path.exists(wal_path):
            continue

        size = os.path.getsize(wal_path)

        # 빈 파일만 정리
        if size == 0:
            logger.warning(f"Removing empty WAL/SHM file: {wal_path}")
            os.remove(wal_path)
            continue

        # 데이터가 있을 수 있는 WAL/SHM은 삭제하지 않음
        age_hours = (time.time() - os.path.getmtime(wal_path)) / 3600
        logger.warning(
            f"Non-empty WAL/SHM detected: {wal_path} "
            f"(size={size} bytes, age={age_hours:.1f}h) - manual review recommended"
        )
