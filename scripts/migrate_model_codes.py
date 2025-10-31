#!/usr/bin/env python3
"""
모델 코드 테이블 마이그레이션 스크립트
- model_codes 테이블 생성
- FTS5 재구성 (tokenchars '-/_.')
- 안전한 원자적 마이그레이션
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def backup_database(db_path: str) -> str:
    """데이터베이스 백업"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"

    logger.info(f"데이터베이스 백업 생성: {backup_path}")
    shutil.copy2(db_path, backup_path)

    return backup_path


def create_model_codes_table(db: MetadataDB):
    """model_codes 테이블 생성"""
    logger.info("model_codes 테이블 생성 중...")

    with db._cursor() as cur:
        # model_codes 테이블
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_codes (
                doc_id    INTEGER NOT NULL,
                code      TEXT    NOT NULL,
                norm_code TEXT    NOT NULL,
                positions TEXT,
                source    TEXT    NOT NULL CHECK(source IN ('filename','content','metadata')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(doc_id, norm_code, source)
            )
        """)

        # 인덱스
        cur.execute("CREATE INDEX IF NOT EXISTS idx_model_codes_norm ON model_codes(norm_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_model_codes_doc_id ON model_codes(doc_id)")

    logger.info("✅ model_codes 테이블 생성 완료")


def rebuild_fts5(db: MetadataDB):
    """FTS5 테이블 재구성 (커스텀 토크나이저)"""
    logger.info("FTS5 테이블 재구성 중...")

    with db._cursor() as cur:
        # 기존 FTS 테이블 삭제
        logger.warning("⚠️ 기존 documents_fts 삭제 (백업됨)")
        cur.execute("DROP TABLE IF EXISTS documents_fts")

        # 새 FTS5 테이블 생성 (tokenchars '-/_.')
        logger.info("새 FTS5 테이블 생성 (tokenchars '-/_.')")
        cur.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                path UNINDEXED,
                title,
                filename,
                text_preview,
                keywords,
                content=documents,
                content_rowid=id,
                tokenize = "unicode61 remove_diacritics 2 tokenchars '-/_.'"
            )
        """)

        # 트리거 재생성
        logger.info("FTS 동기화 트리거 재생성")

        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ai
            AFTER INSERT ON documents
            BEGIN
                INSERT INTO documents_fts(rowid, path, title, filename, text_preview, keywords)
                VALUES (new.id, new.path, new.title, new.filename, new.text_preview, new.keywords);
            END
        """)

        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_au
            AFTER UPDATE ON documents
            BEGIN
                UPDATE documents_fts
                SET title = new.title,
                    filename = new.filename,
                    text_preview = new.text_preview,
                    keywords = new.keywords
                WHERE rowid = new.id;
            END
        """)

        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ad
            AFTER DELETE ON documents
            BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        """)

        # 재색인 (기존 데이터 복사)
        logger.info("FTS 재색인 중...")
        cur.execute("""
            INSERT INTO documents_fts(rowid, path, title, filename, text_preview, keywords)
            SELECT id, path, title, filename, text_preview, keywords FROM documents
        """)

        # 재색인된 행 수 확인
        cur.execute("SELECT COUNT(*) FROM documents_fts")
        count = cur.fetchone()[0]
        logger.info(f"✅ FTS5 재색인 완료: {count}개 문서")

    logger.info("✅ FTS5 테이블 재구성 완료")


def verify_migration(db: MetadataDB):
    """마이그레이션 검증"""
    logger.info("마이그레이션 검증 중...")

    with db._cursor() as cur:
        # 테이블 존재 확인
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('model_codes', 'documents_fts')
        """)
        tables = [row[0] for row in cur.fetchall()]

        if "model_codes" not in tables:
            raise Exception("model_codes 테이블이 생성되지 않았습니다")
        if "documents_fts" not in tables:
            raise Exception("documents_fts 테이블이 생성되지 않았습니다")

        # FTS 토크나이저 테스트
        cur.execute("SELECT * FROM documents_fts WHERE documents_fts MATCH 'pdf' LIMIT 1")
        if not cur.fetchone():
            logger.warning("⚠️ FTS 검색 테스트 실패 (문서가 없을 수 있음)")
        else:
            logger.info("✅ FTS 검색 테스트 성공")

    logger.info("✅ 마이그레이션 검증 완료")


def main():
    """메인 실행 함수"""
    logger.info("=" * 80)
    logger.info("모델 코드 테이블 마이그레이션 시작")
    logger.info("=" * 80)

    db_path = "metadata.db"

    # 백업 생성
    backup_path = backup_database(db_path)
    logger.info(f"백업 경로: {backup_path}")

    try:
        # DB 연결
        db = MetadataDB(db_path=db_path)

        # 1. model_codes 테이블 생성
        create_model_codes_table(db)

        # 2. FTS5 재구성
        rebuild_fts5(db)

        # 3. 검증
        verify_migration(db)

        logger.info("=" * 80)
        logger.info("✅ 마이그레이션 성공")
        logger.info("=" * 80)
        logger.info(f"백업 파일: {backup_path}")
        logger.info("롤백 방법: cp {backup_path} {db_path}")

    except Exception as e:
        logger.error(f"❌ 마이그레이션 실패: {e}")
        logger.error(f"롤백: cp {backup_path} {db_path}")
        raise


if __name__ == "__main__":
    main()
