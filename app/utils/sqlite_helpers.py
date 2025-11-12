#!/usr/bin/env python3
"""
SQLite 연결 유틸리티 v2.0
WAL 모드, busy_timeout, 경합 내성 및 스레드 안정성 확보

개선사항:
1. check_same_thread=False: 멀티스레드 환경 지원
2. executescript: PRAGMA 일괄 설정으로 연결 오버헤드 감소
3. WAL 자동 복구: 비정상 종료로 인한 빈 WAL/SHM 파일 자동 제거
4. 환경변수 제어: SQLITE_SYNC_MODE로 동기화 수준 조정
"""
import logging
import os
import sqlite3
import time
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
        METADB_PATH: DB 파일 경로 (기본: var/metadata.db)
        SQLITE_SYNC_MODE: 동기화 수준 (NORMAL|FULL, 기본: NORMAL)
        SQLITE_CACHE_SIZE: 캐시 크기 KB 단위 (기본: 2000 → 2MB)

    설정:
        - WAL 모드: 동시 읽기/쓰기 허용
        - autocommit: isolation_level=None
        - busy_timeout: 5초 (잠금 대기)
        - check_same_thread: False (멀티스레드 접근 허용)

    주의:
        동일 Connection 객체를 여러 스레드가 동시에 사용하는 것은 금지.
        thread-local storage나 connection pool 사용 권장.
    """
    path = db_path or os.getenv("METADB_PATH", "var/metadata.db")
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

    # PRAGMA 일괄 설정 (성능 최적화)
    conn.executescript(f"""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = {sync_mode};
        PRAGMA busy_timeout = 5000;
        PRAGMA cache_size = -{cache_size};
    """)

    # Row Factory 설정 (dict-like access)
    if enable_row_factory:
        conn.row_factory = sqlite3.Row

    logger.info(
        f"SQLite connected: {path}, WAL=enabled, sync={sync_mode}, cache={cache_size}KB"
    )

    return conn


def _cleanup_stale_wal(db_path: str, max_age_hours: int = 24) -> None:
    """
    비정상 종료로 인한 빈 또는 오래된 WAL/SHM 파일 자동 제거

    Args:
        db_path: DB 파일 경로
        max_age_hours: WAL 파일 최대 보존 시간 (시간 단위)

    처리:
        1. 빈 파일(0 bytes) → 즉시 삭제
        2. 오래된 파일(> max_age_hours) → 삭제

    효과:
        - "database is locked" 에러 회피
        - "database disk image is malformed" 예방
    """
    for suffix in ("-wal", "-shm"):
        wal_path = f"{db_path}{suffix}"

        if not os.path.exists(wal_path):
            continue

        # 빈 파일 제거
        if os.path.getsize(wal_path) == 0:
            logger.warning(f"Removing empty WAL file: {wal_path}")
            os.remove(wal_path)
            continue

        # 오래된 파일 제거 (stale WAL)
        age_hours = (time.time() - os.path.getmtime(wal_path)) / 3600
        if age_hours > max_age_hours:
            logger.warning(
                f"Removing stale WAL file: {wal_path} (age: {age_hours:.1f}h)"
            )
            os.remove(wal_path)
