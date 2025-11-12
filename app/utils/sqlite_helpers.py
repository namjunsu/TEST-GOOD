"""
SQLite 연결 유틸리티
WAL 모드, busy_timeout, 경합 내성 확보
"""
import os
import sqlite3
from typing import Optional


def connect_metadata(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    메타데이터 DB 연결 (경합 내성 강화)

    Args:
        db_path: DB 경로. None이면 환경변수 METADB_PATH 또는 기본값 var/metadata.db 사용

    Returns:
        sqlite3.Connection: WAL/busy_timeout 설정된 연결
    """
    path = db_path or os.getenv("METADB_PATH", "var/metadata.db")

    # isolation_level=None: autocommit 모드 (트랜잭션 관리 단순화)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)

    # WAL(Write-Ahead Logging) 모드: 동시 읽기/쓰기 허용
    conn.execute("PRAGMA journal_mode=WAL;")

    # NORMAL: 동기화 레벨 조정 (성능 향상, WAL과 조합 시 안전)
    conn.execute("PRAGMA synchronous=NORMAL;")

    # busy_timeout: 잠금 대기 최대 5초 (데드락 방지)
    conn.execute("PRAGMA busy_timeout=5000;")

    return conn
