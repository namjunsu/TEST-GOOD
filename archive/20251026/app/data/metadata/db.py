"""메타데이터 데이터베이스 (SQLite with WAL)

WAL 모드 설정으로 동시 읽기 지원:
- 다중 reader (Streamlit 세션)
- 단일 writer (인덱싱)

Example:
    >>> db = MetadataDB()
    >>> db.save_document(doc_id="doc1", title="...", content="...")
    >>> doc = db.get_document("doc1")
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from app.core.logging import get_logger
from app.core.errors import DatabaseError

logger = get_logger(__name__)


# ============================================================================
# 메타데이터 DB
# ============================================================================

class MetadataDB:
    """메타데이터 데이터베이스 (SQLite + WAL)

    Features:
    - WAL 모드: 동시 읽기 지원
    - Connection pool: 읽기/쓰기 분리
    - 자동 스키마 초기화

    Example:
        >>> db = MetadataDB()
        >>> db.save_document("doc1", title="제목", content="내용", metadata={})
        >>> doc = db.get_document("doc1")
        >>> print(doc["title"])
    """

    def __init__(self, db_path: Optional[Path] = None):
        """DB 초기화

        Args:
            db_path: DB 파일 경로 (None이면 metadata.db - 루트 경로 실사용 기준)
        """
        if db_path is None:
            # 실제 DB 위치에 맞춤 (./metadata.db)
            import os
            db_path = Path(os.getenv("DB_METADATA_PATH", "metadata.db"))

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # DB 초기화 및 WAL 모드 설정
        self._init_db()
        logger.info(f"MetadataDB initialized: {self.db_path} (WAL mode enabled)")

    def _init_db(self) -> None:
        """DB 초기화 및 WAL 모드 설정"""
        try:
            with self._get_write_conn() as conn:
                # WAL 모드 활성화 (동시 읽기 지원)
                result = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
                logger.info(f"DB journal_mode set: {result[0] if result else 'unknown'}")

                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")  # 5초

                logger.debug("DB PRAGMA settings applied: WAL mode, busy_timeout=5000ms")

                # 스키마 생성
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        doc_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT  -- JSON
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS query_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query TEXT NOT NULL,
                        result_count INTEGER,
                        latency REAL,
                        success BOOLEAN,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT  -- JSON
                    )
                """)

                # 인덱스
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_documents_title
                    ON documents(title)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_query_logs_created_at
                    ON query_logs(created_at)
                """)

                conn.commit()
                logger.info("Database schema initialized with WAL mode")

        except sqlite3.Error as e:
            msg = "Database initialization failed"
            logger.error(f"{msg}: {e}", exc_info=True)
            raise DatabaseError(msg, details=str(e)) from e

    # ========================================================================
    # Connection Management (Read/Write 분리)
    # ========================================================================

    @contextmanager
    def _get_read_conn(self):
        """읽기 전용 커넥션 (context manager)

        WAL 모드에서 다중 reader 지원.

        Yields:
            sqlite3.Connection: 읽기 전용 커넥션
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row  # dict-like access
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _get_write_conn(self):
        """쓰기 커넥션 (context manager)

        WAL 모드에서 단일 writer만 허용.

        Yields:
            sqlite3.Connection: 쓰기 커넥션
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ========================================================================
    # Document CRUD
    # ========================================================================

    def save_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """문서 저장 (INSERT or UPDATE)

        Args:
            doc_id: 문서 ID (고유)
            title: 제목
            content: 본문
            source: 출처
            metadata: 추가 메타데이터 (JSON)
        """
        import json

        try:
            with self._get_write_conn() as conn:
                metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO documents (doc_id, title, content, source, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        title = excluded.title,
                        content = excluded.content,
                        source = excluded.source,
                        metadata = excluded.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (doc_id, title, content, source, metadata_json),
                )
                conn.commit()
                logger.debug(f"Document saved: {doc_id}")

        except sqlite3.Error as e:
            msg = "Failed to save document"
            logger.error(f"{msg}: {doc_id}, {e}", exc_info=True)
            raise DatabaseError(msg, details=str(e)) from e

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """문서 조회

        Args:
            doc_id: 문서 ID

        Returns:
            문서 데이터 (dict) 또는 None
        """
        import json

        try:
            with self._get_read_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM documents WHERE doc_id = ?",
                    (doc_id,),
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                doc = dict(row)
                # JSON 파싱
                if doc.get("metadata"):
                    doc["metadata"] = json.loads(doc["metadata"])

                return doc

        except sqlite3.Error as e:
            msg = "Failed to get document"
            logger.error(f"{msg}: {doc_id}, {e}", exc_info=True)
            raise DatabaseError(msg, details=str(e)) from e

    def list_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """문서 목록 조회

        Args:
            limit: 최대 개수

        Returns:
            문서 목록
        """
        import json

        try:
            with self._get_read_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()

                docs = []
                for row in rows:
                    doc = dict(row)
                    if doc.get("metadata"):
                        doc["metadata"] = json.loads(doc["metadata"])
                    docs.append(doc)

                return docs

        except sqlite3.Error as e:
            msg = "Failed to list documents"
            logger.error(f"{msg}: {e}", exc_info=True)
            raise DatabaseError(msg, details=str(e)) from e

    # ========================================================================
    # Query Log
    # ========================================================================

    def log_query(
        self,
        query: str,
        result_count: int,
        latency: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """쿼리 로그 저장

        Args:
            query: 질의 텍스트
            result_count: 결과 개수
            latency: 실행 시간
            success: 성공 여부
            metadata: 추가 정보
        """
        import json

        try:
            with self._get_write_conn() as conn:
                metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO query_logs (query, result_count, latency, success, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (query, result_count, latency, success, metadata_json),
                )
                conn.commit()
                logger.debug(f"Query logged: {query[:50]}, latency={latency:.2f}s")

        except sqlite3.Error as e:
            # 로그 실패는 치명적이지 않으므로 경고만
            logger.warning(f"Failed to log query: {e}")

    def get_recent_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """최근 쿼리 조회

        Args:
            limit: 최대 개수

        Returns:
            쿼리 로그 목록
        """
        import json

        try:
            with self._get_read_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM query_logs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()

                logs = []
                for row in rows:
                    log = dict(row)
                    if log.get("metadata"):
                        log["metadata"] = json.loads(log["metadata"])
                    logs.append(log)

                return logs

        except sqlite3.Error as e:
            msg = "Failed to get recent queries"
            logger.error(f"{msg}: {e}", exc_info=True)
            raise DatabaseError(msg, details=str(e)) from e
