"""SQLite 호환 래퍼 - 기존 코드의 sqlite3.connect() 호출을 일원화

이 래퍼를 통해 모든 DB 연결이 WAL 모드, busy_timeout 등의
설정을 자동으로 적용받도록 합니다.

사용법:
    기존:
        import sqlite3
        conn = sqlite3.connect("database.db")

    변경:
        from app.data.metadata import db_compat as sqlite3
        conn = sqlite3.connect("database.db")

    또는 명시적으로:
        from app.data.metadata.db_compat import connect
        conn = connect("database.db", read_only=True)
"""

from __future__ import annotations

import sqlite3 as _sqlite3
from pathlib import Path
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


def connect(
    database: str | Path,
    timeout: float = 5.0,
    check_same_thread: bool = False,
    read_only: bool = False,
    **kwargs: Any,
) -> _sqlite3.Connection:
    """SQLite 연결 (WAL 모드 + busy_timeout 자동 적용)

    Args:
        database: DB 파일 경로 (":memory:" 가능)
        timeout: busy timeout (초, 기본 5초)
        check_same_thread: 스레드 체크 비활성화 (Streamlit용, 기본 False)
        read_only: 읽기 전용 모드 (True: SELECT만, False: 쓰기 가능)
        **kwargs: 추가 sqlite3.connect 인자

    Returns:
        sqlite3.Connection: 설정된 DB 연결
    """
    # 특수 DB는 그대로 연결
    if database == ":memory:":
        conn = _sqlite3.connect(
            database,
            timeout=timeout,
            check_same_thread=check_same_thread,
            **kwargs,
        )
        logger.debug("In-memory DB 연결")
        return conn

    # 파일 경로 정규화
    db_path = Path(database)

    # var/db 하위로 강제 (선택적 - 주석 처리 가능)
    # if not str(db_path).startswith("var/db/"):
    #     logger.warning(f"DB 파일이 var/db 외부: {db_path}")

    # DB 디렉터리 생성
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # 연결
    conn = _sqlite3.connect(
        str(db_path),
        timeout=timeout,
        check_same_thread=check_same_thread,
        **kwargs,
    )

    # WAL 모드 설정 (읽기 전용이 아닐 경우)
    if not read_only:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
            logger.debug(f"DB 연결 (WAL 모드): {db_path}")
        except Exception as e:
            logger.warning(f"WAL 모드 설정 실패 (읽기 전용일 수도 있음): {e}")
    else:
        logger.debug(f"DB 연결 (읽기 전용): {db_path}")

    # Row factory 설정 (dict-like 접근)
    conn.row_factory = _sqlite3.Row

    return conn


# sqlite3 모듈 호환성을 위한 추가 export
Row = _sqlite3.Row
Error = _sqlite3.Error
IntegrityError = _sqlite3.IntegrityError
OperationalError = _sqlite3.OperationalError
DatabaseError = _sqlite3.DatabaseError
ProgrammingError = _sqlite3.ProgrammingError
NotSupportedError = _sqlite3.NotSupportedError


# 모듈 레벨 __all__
__all__ = [
    "connect",
    "Row",
    "Error",
    "IntegrityError",
    "OperationalError",
    "DatabaseError",
    "ProgrammingError",
    "NotSupportedError",
]
