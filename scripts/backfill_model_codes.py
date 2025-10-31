#!/usr/bin/env python3
"""
기존 문서에 대한 model_codes 소급 적용 (backfill)
모든 documents 테이블 문서에서 코드를 추출하여 model_codes에 삽입
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.textproc.normalizer import extract_codes, normalize_code
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def backfill_model_codes():
    """기존 문서에 대한 코드 소급 적용"""
    logger.info("=" * 80)
    logger.info("model_codes 소급 적용 시작")
    logger.info("=" * 80)

    # DB 연결
    db = MetadataDB(db_path="metadata.db")

    # 모든 문서 조회
    conn = db._get_conn()
    cursor = conn.execute("SELECT id, filename, text_preview FROM documents")
    documents = cursor.fetchall()

    logger.info(f"처리 대상: {len(documents)}개 문서")

    total_codes = 0
    processed = 0
    skipped = 0

    for doc in documents:
        doc_id, filename, text_preview = doc
        codes_inserted = 0

        try:
            # 파일명에서 코드 추출
            filename_codes = extract_codes(filename, normalize_result=True)
            for code in filename_codes:
                norm_code = normalize_code(code)
                _insert_model_code(conn, doc_id, code, norm_code, source="filename")
                codes_inserted += 1

            # 본문에서 코드 추출
            if text_preview:
                content_codes = extract_codes(text_preview, normalize_result=True)
                content_codes_unique = [c for c in content_codes if c not in filename_codes]

                for code in content_codes_unique:
                    norm_code = normalize_code(code)
                    _insert_model_code(conn, doc_id, code, norm_code, source="content")
                    codes_inserted += 1

            if codes_inserted > 0:
                logger.info(f"📝 doc_id={doc_id}, filename={filename}, codes={codes_inserted}")
                total_codes += codes_inserted
                processed += 1
            else:
                skipped += 1

        except Exception as e:
            logger.error(f"처리 실패: doc_id={doc_id}, {e}")
            skipped += 1

    conn.commit()

    # 결과 요약
    logger.info("=" * 80)
    logger.info("소급 적용 완료")
    logger.info("=" * 80)
    logger.info(f"처리된 문서: {processed}개")
    logger.info(f"건너뛴 문서: {skipped}개")
    logger.info(f"추출된 코드: {total_codes}개")

    # 검증
    cursor = conn.execute("SELECT COUNT(*) FROM model_codes")
    total_entries = cursor.fetchone()[0]
    logger.info(f"model_codes 테이블 총 레코드: {total_entries}개")


def _insert_model_code(conn, doc_id: int, code: str, norm_code: str, source: str):
    """model_codes 테이블에 코드 삽입"""
    try:
        conn.execute("""
            INSERT OR IGNORE INTO model_codes (doc_id, code, norm_code, source)
            VALUES (?, ?, ?, ?)
        """, (doc_id, code, norm_code, source))
    except Exception as e:
        logger.error(f"삽입 실패: doc_id={doc_id}, code={code}, {e}")


if __name__ == "__main__":
    backfill_model_codes()
