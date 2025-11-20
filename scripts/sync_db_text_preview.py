#!/usr/bin/env python3
"""
metadata.db의 text_preview를 data/extracted/*.txt 파일 기반으로 동기화
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sqlite3
from app.core.logging import get_logger

logger = get_logger(__name__)

EXTRACTED_DIR = BASE_DIR / "data" / "extracted"
DB_PATH = BASE_DIR / "metadata.db"


def sync_text_previews():
    """txt 파일 기반으로 text_preview 동기화"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 모든 문서 가져오기
    cursor.execute("SELECT id, filename FROM documents")
    documents = cursor.fetchall()

    updated = 0
    skipped = 0
    failed = 0

    logger.info("=" * 80)
    logger.info("metadata.db text_preview 동기화 시작")
    logger.info("=" * 80)
    logger.info(f"총 문서: {len(documents)}개")

    for doc_id, filename in documents:
        # txt 파일 경로
        txt_filename = Path(filename).stem + ".txt"
        txt_file = EXTRACTED_DIR / txt_filename

        if not txt_file.exists():
            skipped += 1
            continue

        try:
            # txt 파일 읽기
            text = txt_file.read_text(encoding='utf-8')

            # 처음 500자만 미리보기로 저장
            preview = text[:500].strip()

            if not preview:
                skipped += 1
                continue

            # DB 업데이트
            cursor.execute(
                "UPDATE documents SET text_preview = ? WHERE id = ?",
                (preview, doc_id)
            )

            updated += 1

            if updated % 50 == 0:
                logger.info(f"진행: {updated}개 업데이트됨")

        except Exception as e:
            logger.error(f"실패: {filename} - {e}")
            failed += 1

    conn.commit()
    conn.close()

    # 결과
    logger.info("\n" + "=" * 80)
    logger.info("📊 결과")
    logger.info("=" * 80)
    logger.info(f"업데이트: {updated}개")
    logger.info(f"건너뜀: {skipped}개 (txt 파일 없음)")
    logger.info(f"실패: {failed}개")
    logger.info("=" * 80)

    return updated, skipped, failed


def main():
    updated, skipped, failed = sync_text_previews()

    if updated > 0:
        logger.info("\n✅ 동기화 완료")
        logger.info("\n확인:")
        logger.info("  sqlite3 metadata.db \"SELECT filename, length(text_preview) FROM documents LIMIT 10\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())
