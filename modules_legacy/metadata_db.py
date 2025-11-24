#!/usr/bin/env python3
"""
Phase 1.2: 메타데이터 DB 구축
SQLite를 사용한 PDF 메타데이터 관리
"""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetadataDB:
    """PDF 메타데이터 SQLite DB 관리"""

    def __init__(self, db_path: str = "metadata.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._docs_root = Path("docs").resolve()  # 문서 루트 경로
        self.init_database()
        logger.info(f"MetadataDB 초기화 (thread-safe): {db_path}")

    def _new_conn(self) -> sqlite3.Connection:
        """새 SQLite 연결 생성 (스레드별)"""
        conn = sqlite3.connect(
            f"file:{self._db_path}?cache=shared",
            uri=True,
            check_same_thread=False,
            isolation_level=None,
            timeout=30
        )
        conn.row_factory = sqlite3.Row

        # Performance optimizations (memory tuning)
        # Note: journal_mode를 강제하지 않음 - 기존 설정 유지
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA mmap_size=1073741824;")   # 1GB mmap (메모리 압박 방지)
        conn.execute("PRAGMA cache_size=-524288;")     # ~512MB cache (negative = KB)
        conn.execute("PRAGMA page_size=4096;")
        conn.execute("PRAGMA analysis_limit=400;")

        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """현재 스레드의 연결 반환 (없으면 생성)"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_conn()
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self):
        """커서 컨텍스트 매니저 (안전한 commit/close)"""
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _normalize_path(self, path: str) -> str:
        """
        상대 경로 정규화 헬퍼
        docs/foo.pdf → foo.pdf
        /abs/path/docs/foo.pdf → foo.pdf
        """
        try:
            p = Path(path).resolve()
            rel = p.relative_to(self._docs_root)
            return str(rel)
        except ValueError:
            # docs 밖: 그대로 반환 + 경고
            logger.warning(f"⚠️ PDF path outside docs: {path}")
            return path

    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        # 초기 연결 생성 (스레드 로컬)
        conn = self._get_conn()
        logger.info(f"DB WAL mode enabled: {self._db_path}")

        with self._cursor() as cur:
            # 메타데이터 테이블 생성
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    title TEXT,
                    date TEXT,
                    year TEXT,
                    month TEXT,
                    category TEXT,
                    drafter TEXT,
                    amount INTEGER,
                    file_size INTEGER,
                    page_count INTEGER,
                    text_preview TEXT,
                    keywords TEXT,  -- JSON array
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 인덱스 생성 (검색 성능 향상)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_year ON documents(year)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_category ON documents(category)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON documents(date)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_filename ON documents(filename)"
            )

            # 전문 검색을 위한 FTS 테이블 (Full-Text Search)
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(
                    path UNINDEXED,
                    title,
                    text_preview,
                    keywords,
                    content=documents,
                    content_rowid=id
                )
            """
            )

            # FTS 트리거 설정 (자동 동기화)
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ai
                AFTER INSERT ON documents
                BEGIN
                    INSERT INTO documents_fts(rowid, path, title, text_preview, keywords)
                    VALUES (new.id, new.path, new.title, new.text_preview, new.keywords);
                END
            """
            )

            # FTS5 external content 모드에서는 UPDATE 대신 DELETE+INSERT 패턴 권장
            cur.execute("DROP TRIGGER IF EXISTS documents_au")
            cur.execute(
                """
                CREATE TRIGGER documents_au
                AFTER UPDATE ON documents
                BEGIN
                    DELETE FROM documents_fts WHERE rowid = new.id;
                    INSERT INTO documents_fts(rowid, path, title, text_preview, keywords)
                    VALUES (new.id, new.path, new.title, new.text_preview, new.keywords);
                END
            """
            )

            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ad
                AFTER DELETE ON documents
                BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            """
            )

        # 스키마 마이그레이션: doctype, display_date, claimed_total, sum_match 컬럼 추가
        self._migrate_schema()

    def _migrate_schema(self):
        """스키마 마이그레이션: 신규 컬럼 추가"""
        try:
            # 백업 생성
            backup_path = f"{self._db_path}.bak"
            import shutil

            if Path(self._db_path).exists() and not Path(backup_path).exists():
                shutil.copy2(self._db_path, backup_path)
                logger.info(f"DB 백업 생성: {backup_path}")

            with self._cursor() as cur:
                # doctype 컬럼 추가 (존재 확인 후 추가)
                cur.execute("PRAGMA table_info(documents)")
                columns = [col[1] for col in cur.fetchall()]

                if "doctype" not in columns:
                    cur.execute(
                        'ALTER TABLE documents ADD COLUMN doctype TEXT DEFAULT "proposal"'
                    )
                    logger.info("✓ doctype 컬럼 추가")

                if "display_date" not in columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN display_date TEXT")
                    logger.info("✓ display_date 컬럼 추가")

                if "claimed_total" not in columns:
                    cur.execute(
                        "ALTER TABLE documents ADD COLUMN claimed_total INTEGER"
                    )
                    logger.info("✓ claimed_total 컬럼 추가")

                if "sum_match" not in columns:
                    cur.execute("ALTER TABLE documents ADD COLUMN sum_match BOOLEAN")
                    logger.info("✓ sum_match 컬럼 추가")

        except Exception as e:
            logger.error(f"스키마 마이그레이션 실패: {e}")

    def add_document(self, metadata: Dict[str, Any]) -> int:
        """문서 메타데이터 추가"""
        try:
            # 키워드를 JSON 문자열로 변환
            keywords = metadata.get("keywords", [])
            if isinstance(keywords, list):
                keywords = json.dumps(keywords, ensure_ascii=False)

            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO documents (
                        path, filename, title, date, year, month, category,
                        drafter, amount, file_size, page_count, text_preview, keywords,
                        doctype, display_date, claimed_total, sum_match
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        self._normalize_path(str(metadata.get("path", ""))),
                        metadata.get("filename", ""),
                        metadata.get("title", ""),
                        metadata.get("date", ""),
                        metadata.get("year", ""),
                        metadata.get("month", ""),
                        metadata.get("category", ""),
                        metadata.get("drafter", ""),
                        metadata.get("amount", 0),
                        metadata.get("file_size", 0),
                        metadata.get("page_count", 0),
                        metadata.get("text_preview", ""),
                        keywords,
                        metadata.get("doctype", "proposal"),
                        metadata.get("display_date", ""),
                        metadata.get("claimed_total", None),
                        metadata.get("sum_match", None),
                    ),
                )
                return cur.lastrowid

        except Exception as e:
            logger.error(f"문서 추가 실패: {e}")
            return -1

    def search_by_year(self, year: str) -> List[Dict[str, Any]]:
        """연도별 검색"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE year = ? ORDER BY COALESCE(display_date, date) DESC", (year,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_documents(
        self, drafter: Optional[str] = None, year: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """다중 필터 검색 (drafter, year 조합 지원)

        Args:
            drafter: 기안자명 (부분 일치)
            year: 연도 (display_date 기준, 예: "2024")
            limit: 최대 결과 수

        Returns:
            검색 결과 리스트 (날짜 내림차순)
        """
        query = "SELECT * FROM documents WHERE 1=1"
        params = []

        if drafter:
            query += " AND drafter LIKE ?"
            params.append(f"%{drafter}%")

        if year:
            # display_date 또는 date 필드에서 연도 추출
            query += " AND (display_date LIKE ? OR date LIKE ?)"
            params.append(f"{year}%")
            params.append(f"{year}%")

        query += " ORDER BY COALESCE(display_date, date) DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        conn = self._get_conn()
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def count_documents(
        self, drafter: Optional[str] = None, year: Optional[str] = None
    ) -> int:
        """문서 개수 조회 (필터 적용)

        Args:
            drafter: 기안자명 (부분 일치)
            year: 연도 (display_date 기준, 예: "2024")

        Returns:
            조건에 맞는 문서 개수
        """
        query = "SELECT COUNT(*) as count FROM documents WHERE 1=1"
        params = []

        if drafter:
            query += " AND drafter LIKE ?"
            params.append(f"%{drafter}%")

        if year:
            # display_date 또는 date 필드에서 연도 추출
            query += " AND (display_date LIKE ? OR date LIKE ?)"
            params.append(f"{year}%")
            params.append(f"{year}%")

        conn = self._get_conn()
        cursor = conn.execute(query, params)
        result = cursor.fetchone()
        return result["count"] if result else 0

    def search_by_category(self, category: str) -> List[Dict[str, Any]]:
        """카테고리별 검색"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE category LIKE ? ORDER BY COALESCE(display_date, date) DESC",
            (f"%{category}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """키워드 검색 (FTS5 BM25 스코어링 사용, syntax error 안전 처리)"""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                SELECT d.*, bm25(documents_fts) AS score
                FROM documents d
                JOIN documents_fts f ON d.id = f.rowid
                WHERE documents_fts MATCH ?
                ORDER BY score ASC
                LIMIT ?
            """,
                (keyword, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            # FTS5 syntax error (예: "A AND", " ", 빈 문자열 등)
            if "fts5" in str(e).lower() or "syntax" in str(e).lower():
                logger.warning(f"FTS5 검색 syntax 오류 (keyword='{keyword}'): {e}")
                return []
            else:
                raise  # 다른 OperationalError는 재발생

    def search_by_date_range(
        self, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """날짜 범위 검색"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE date BETWEEN ? AND ? ORDER BY COALESCE(display_date, date) DESC",
            (start_date, end_date),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_document_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """경로로 문서 조회"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE path = ?", (str(path),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_document(self, filename: str) -> Optional[Dict[str, Any]]:
        """파일명으로 문서 조회 (perfect_rag.py 호환용)"""
        # 파일명만으로 검색
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE filename = ? LIMIT 1", (filename,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """파일명으로 문서 조회 (claimed_total 포함, 대소문자 무시)

        Args:
            filename: 파일명 (확장자 포함 가능)

        Returns:
            문서 딕셔너리 (claimed_total 포함) 또는 None
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM documents WHERE filename = ? COLLATE NOCASE LIMIT 1",
            (filename,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_by_filename_fuzzy(self, name: str) -> Optional[Dict[str, Any]]:
        """퍼지 매칭으로 파일명 검색 (언더스코어/공백/특수기호 무시)

        Args:
            name: 검색할 파일명 (일부만 입력 가능)

        Returns:
            가장 유사한 문서 딕셔너리 또는 None
        """
        # 이모지와 메타데이터 제거 (🏷, 📅, ✍ 등)
        # "뉴스 스튜디오 지미집 Control Box 수리 건 🏷 proposal · 📅 2024-11-25 · ✍ 남준수"
        # -> "뉴스 스튜디오 지미집 Control Box 수리 건"
        clean_name = re.sub(r"[🏷📅✍·].*$", "", name).strip()

        def slug(s):
            """문자열 정규화: 소문자 + 특수기호 제거"""
            s = s.lower().replace("&", "and")
            # 공백과 언더스코어를 모두 제거하여 비교
            return re.sub(r"[^0-9a-z가-힣]", "", s)

        s = slug(clean_name)

        # 빈 문자열이면 None 반환
        if not s:
            return None

        conn = self._get_conn()
        cur = conn.cursor()
        # SQL에서도 모든 특수문자 제거하여 비교
        cur.execute(
            """
            SELECT *,
              ABS(LENGTH(filename) - ?) AS len_diff
            FROM documents
            WHERE LOWER(REPLACE(REPLACE(REPLACE(REPLACE(filename, '_',''), ' ',''), '.pdf',''), '-','')) LIKE ?
            ORDER BY len_diff ASC
            LIMIT 1
            """,
            (len(clean_name), f"%{s}%"),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_text_preview(self, filename: str) -> Optional[str]:
        """파일명으로 text_preview 조회 (snippet 보강용)

        Args:
            filename: 파일명 (확장자 포함 가능)

        Returns:
            text_preview 문자열 또는 None
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT text_preview FROM documents WHERE filename = ? COLLATE NOCASE LIMIT 1",
            (filename,)
        )
        row = cursor.fetchone()
        return row["text_preview"] if row and row["text_preview"] else None

    def get_page_text(self, doc_id: str, page: int) -> Optional[str]:
        """특정 문서의 특정 페이지 텍스트 추출 (캐시 지원)

        Args:
            doc_id: 문서 ID (filename 또는 path)
            page: 페이지 번호 (1-based)

        Returns:
            페이지 텍스트 또는 None
        """
        try:
            # 문서 경로 조회
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT path FROM documents WHERE filename = ? OR path = ? LIMIT 1",
                (doc_id, self._normalize_path(doc_id))
            )
            row = cursor.fetchone()

            if not row:
                logger.debug(f"문서를 찾을 수 없음: {doc_id}")
                return None

            pdf_path = Path(row["path"])

            if not pdf_path.exists():
                logger.debug(f"PDF 파일 없음: {pdf_path}")
                return None

            # PDF에서 페이지 추출 (pdfplumber 사용)
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    if page < 1 or page > len(pdf.pages):
                        logger.debug(f"페이지 범위 초과: {page} (총 {len(pdf.pages)}쪽)")
                        return None

                    page_obj = pdf.pages[page - 1]  # 0-based index
                    text = page_obj.extract_text() or ""

                    logger.debug(f"페이지 추출 성공: {doc_id} page={page}, len={len(text)}")
                    return text.strip()

            except Exception as e:
                logger.error(f"PDF 페이지 추출 실패: {pdf_path} page={page}, error={e}")
                return None

        except Exception as e:
            logger.error(f"get_page_text 실패: doc_id={doc_id}, page={page}, error={e}")
            return None

    def update_document(self, filename: str, **kwargs):
        """문서 메타데이터 간편 업데이트 (perfect_rag.py 호환용)"""
        # 먼저 문서 찾기
        doc = self.get_document(filename)

        if not doc:
            # 새 문서면 추가
            metadata = {"filename": filename}
            metadata.update(kwargs)
            return self.add_document(metadata)

        # 기존 문서 업데이트
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in [
                "title",
                "date",
                "year",
                "month",
                "category",
                "drafter",
                "amount",
                "file_size",
                "page_count",
                "text_preview",
                "keywords",
                "doctype",
                "display_date",
                "claimed_total",
                "sum_match",
            ]:
                fields.append(f"{key} = ?")
                if key == "keywords" and isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                values.append(value)

        if fields:
            values.append(doc["id"])
            query = f"UPDATE documents SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            with self._cursor() as cur:
                cur.execute(query, values)

    def update_text_preview(self, path: str, text_preview: str):
        """텍스트 미리보기 업데이트"""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE documents SET text_preview = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (text_preview[:1000], self._normalize_path(str(path))),  # 최대 1000자
            )

    def get_statistics(self) -> Dict[str, Any]:
        """DB 통계 정보"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) as total FROM documents")
        total = cursor.fetchone()["total"]

        cursor = conn.execute(
            """
            SELECT year, COUNT(*) as count
            FROM documents
            GROUP BY year
            ORDER BY year DESC
        """
        )
        by_year = {row["year"]: row["count"] for row in cursor.fetchall()}

        cursor = conn.execute(
            """
            SELECT category, COUNT(*) as count
            FROM documents
            GROUP BY category
            ORDER BY count DESC
        """
        )
        by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

        return {
            "total_documents": total,
            "by_year": by_year,
            "by_category": by_category,
        }

    def rebuild_fts_index(self):
        """FTS 인덱스 재구축"""
        with self._cursor() as cur:
            cur.execute('INSERT INTO documents_fts(documents_fts) VALUES("rebuild")')
        logger.info("FTS 인덱스 재구축 완료")

    def list_unique_drafters(self) -> set:
        """DB에 존재하는 고유 기안자 목록 반환 (Closed-World Validation용)

        Returns:
            set: 고유 기안자 이름 집합
        """
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                SELECT DISTINCT drafter
                FROM documents
                WHERE drafter IS NOT NULL
                  AND drafter != ''
                  AND drafter != '미상'
                  AND drafter != '작성자 미상'
            """)
            drafters = {row["drafter"] for row in cursor.fetchall()}
            logger.info(f"✅ 고유 기안자 {len(drafters)}명 로드")
            return drafters
        except Exception as e:
            logger.error(f"기안자 목록 조회 실패: {e}")
            return set()

    def close(self):
        """데이터베이스 연결 종료 (모든 스레드 로컬 연결 종료)"""
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None

    def count_unique_documents(self, allowed_ext=("pdf", "txt")) -> int:
        """고유 문서 수 카운트 (중복 제거, 확장자 필터)

        Args:
            allowed_ext: 허용 확장자 튜플 (기본: pdf, txt)

        Returns:
            고유 문서 수
        """
        try:
            # 확장자 조건 생성
            ext_conditions = []
            for ext in allowed_ext:
                ext_conditions.append(f"LOWER(filename) LIKE '%.{ext}'")
            ext_where = f"({' OR '.join(ext_conditions)})" if ext_conditions else "1=1"

            # 고유 문서 카운트 (중복 제거)
            query = f"""
                SELECT COUNT(DISTINCT filename) as count
                FROM documents
                WHERE {ext_where}
            """

            conn = self._get_conn()
            cursor = conn.execute(query)
            result = cursor.fetchone()
            return result["count"] if result else 0

        except Exception as e:
            logger.error(f"고유 문서 카운트 실패: {e}")
            return 0

    def count_by_extension(self) -> dict:
        """확장자별 문서 수 카운트 (물리 파일 기준)

        Returns:
            {'pdf': N, 'txt': M, 'others': K} 형태의 딕셔너리
        """
        try:
            import json
            import os

            # config.indexing import 시도 (없으면 폴백)
            try:
                from config.indexing import DB_PATHS
                file_index_path = DB_PATHS.get("file_index", "file_index.json")
            except (ImportError, KeyError, AttributeError):
                logger.warning("config.indexing 로드 실패, 기본 경로 사용")
                file_index_path = "file_index.json"

            if os.path.exists(file_index_path):
                with open(file_index_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)

                counts = {"pdf": 0, "txt": 0, "others": 0}

                # 파일별로 확장자 카운트
                for file_info in file_data.get("files", []):
                    filename = file_info.get("name", "").lower()
                    if filename.endswith(".pdf"):
                        counts["pdf"] += 1
                    elif filename.endswith(".txt"):
                        counts["txt"] += 1
                    else:
                        counts["others"] += 1

                return counts
            else:
                # file_index.json이 없으면 DB에서 카운트
                counts = {"pdf": 0, "txt": 0, "others": 0}

                conn = self._get_conn()
                cursor = conn.execute("""
                    SELECT
                        LOWER(filename) as fname
                    FROM documents
                """)

                for row in cursor:
                    fname = row["fname"]
                    if fname.endswith(".pdf"):
                        counts["pdf"] += 1
                    elif fname.endswith(".txt"):
                        counts["txt"] += 1
                    else:
                        counts["others"] += 1

                return counts

        except Exception as e:
            logger.error(f"확장자별 카운트 실패: {e}")
            return {"pdf": 0, "txt": 0, "others": 0}

    def count_search_index(self) -> int:
        """검색 인덱스에 등록된 고유 문서 수

        Returns:
            검색 가능한 고유 문서 수
        """
        try:
            import os
            import sqlite3

            from config.indexing import DB_PATHS

            # everything_index.db에서 검색 가능 문서 수 조회
            index_db_path = DB_PATHS.get("everything_index", "everything_index.db")

            if os.path.exists(index_db_path):
                index_conn = sqlite3.connect(index_db_path)
                index_conn.row_factory = sqlite3.Row

                # 고유 파일명 기준으로 카운트
                cursor = index_conn.execute("""
                    SELECT COUNT(DISTINCT filename) as count
                    FROM files
                """)

                result = cursor.fetchone()
                index_conn.close()

                return result["count"] if result else 0
            else:
                # everything_index.db가 없으면 metadata.db 사용
                return self.count_unique_documents()

        except Exception as e:
            logger.error(f"검색 인덱스 카운트 실패: {e}")
            # 폴백: metadata.db의 고유 문서 수 반환
            return self.count_unique_documents()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def extract_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """파일명에서 메타데이터 추출"""
    metadata = {
        "filename": filename,
        "title": "",
        "date": "",
        "year": "",
        "month": "",
        "category": "",
        "drafter": "",
    }

    # 날짜 추출 (YYYY-MM-DD or YYYY-MM or YYYY)
    date_match = re.search(r"(\d{4})[-_]?(\d{2})?[-_]?(\d{2})?", filename)
    if date_match:
        year = date_match.group(1)
        month = date_match.group(2) or ""
        day = date_match.group(3) or ""

        metadata["year"] = year
        metadata["month"] = month

        if day:
            metadata["date"] = f"{year}-{month}-{day}"
        elif month:
            metadata["date"] = f"{year}-{month}"
        else:
            metadata["date"] = year

    # 카테고리 추출
    categories = ["구매", "수리", "보수", "교체", "폐기", "검토", "기술", "소모품"]
    for cat in categories:
        if cat in filename:
            metadata["category"] = cat
            break

    # 제목 추출 (언더스코어를 공백으로)
    title_part = filename.replace(".pdf", "").replace(".PDF", "")
    # 날짜 부분 제거
    title_part = re.sub(r"\d{4}[-_]?\d{2}[-_]?\d{2}[-_]?", "", title_part)
    title_part = title_part.replace("_", " ").strip()
    metadata["title"] = title_part

    return metadata
