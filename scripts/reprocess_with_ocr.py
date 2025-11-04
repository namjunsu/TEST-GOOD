#!/usr/bin/env python3
"""
기존 문서 OCR 재처리 스크립트
페이지당 평균 300자 미만인 문서를 OCR로 재처리합니다.

사용법:
    python scripts/reprocess_with_ocr.py                  # 전체 재처리
    python scripts/reprocess_with_ocr.py --limit 10       # 최대 10개만
    python scripts/reprocess_with_ocr.py --dry-run        # 시뮬레이션만
    python scripts/reprocess_with_ocr.py --threshold 200  # 임계값 변경
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def find_ocr_candidates(
    db_path: str = "metadata.db",
    threshold: int = 300,
    limit: int = None
) -> List[Dict[str, Any]]:
    """OCR이 필요한 문서 목록 조회

    Args:
        db_path: 데이터베이스 경로
        threshold: 페이지당 평균 글자수 임계값
        limit: 최대 처리 개수

    Returns:
        문서 정보 리스트
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            id,
            path,
            filename,
            page_count,
            LENGTH(text_preview) as text_len,
            CAST(LENGTH(text_preview) AS FLOAT) / NULLIF(page_count, 0) as avg_per_page,
            doctype,
            date
        FROM documents
        WHERE page_count > 0
          AND text_preview IS NOT NULL
          AND LENGTH(text_preview) > 0
          AND (CAST(LENGTH(text_preview) AS FLOAT) / page_count) < ?
        ORDER BY avg_per_page ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (threshold,))
    rows = cursor.fetchall()

    candidates = []
    for row in rows:
        candidates.append({
            'id': row['id'],
            'path': row['path'],
            'filename': row['filename'],
            'page_count': row['page_count'],
            'text_len': row['text_len'],
            'avg_per_page': row['avg_per_page'],
            'doctype': row['doctype'],
            'date': row['date']
        })

    conn.close()
    return candidates


def ocr_extract_pdf(pdf_path: Path) -> str:
    """PDF에서 OCR로 텍스트 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        추출된 텍스트
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path

        logger.info(f"OCR 추출 시작: {pdf_path.name}")

        # PDF → 이미지 변환
        images = convert_from_path(str(pdf_path))
        text_pages = []

        # 각 페이지 OCR
        for i, image in enumerate(images, 1):
            logger.debug(f"  페이지 {i}/{len(images)} OCR 중...")
            text = pytesseract.image_to_string(image, lang="kor+eng")
            if text.strip():
                text_pages.append(text)

        full_text = "\n\n".join(text_pages)
        logger.info(f"OCR 완료: {pdf_path.name}, {len(full_text)}자 추출")

        return full_text

    except ImportError as e:
        logger.error(f"OCR 라이브러리 미설치: {e}")
        logger.error("설치 방법: pip install pytesseract pdf2image")
        return ""
    except Exception as e:
        logger.error(f"OCR 추출 실패: {pdf_path.name} - {e}")
        return ""


def update_document_text(
    doc_id: int,
    new_text: str,
    db_path: str = "metadata.db",
    extracted_dir: Path = None
) -> bool:
    """문서의 텍스트 정보 업데이트

    Args:
        doc_id: 문서 ID
        new_text: 새로운 텍스트
        db_path: 데이터베이스 경로
        extracted_dir: 추출된 텍스트 저장 디렉토리

    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # text_preview 업데이트 (처음 500자)
        text_preview = new_text[:500]

        cursor.execute("""
            UPDATE documents
            SET text_preview = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (text_preview, doc_id))

        conn.commit()
        conn.close()

        # 추출 텍스트 파일도 업데이트
        if extracted_dir:
            conn2 = sqlite3.connect(db_path)
            cursor2 = conn2.cursor()
            cursor2.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
            row = cursor2.fetchone()
            conn2.close()

            if row:
                filename = row[0]
                txt_filename = filename.replace('.pdf', '.txt')
                txt_path = extracted_dir / txt_filename

                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(new_text)

                logger.debug(f"텍스트 파일 업데이트: {txt_path}")

        return True

    except Exception as e:
        logger.error(f"DB 업데이트 실패 (doc_id={doc_id}): {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="기존 문서 OCR 재처리 스크립트"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=300,
        help="페이지당 평균 글자수 임계값 (기본: 300)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="최대 처리 개수"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 처리 없이 시뮬레이션만"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="metadata.db",
        help="데이터베이스 경로 (기본: metadata.db)"
    )

    args = parser.parse_args()

    # 추출 텍스트 디렉토리
    extracted_dir = Path("data/extracted")
    extracted_dir.mkdir(parents=True, exist_ok=True)

    logger.info("="*80)
    logger.info("기존 문서 OCR 재처리 시작")
    logger.info("="*80)
    logger.info(f"임계값: {args.threshold}자/페이지")
    logger.info(f"제한: {args.limit or '없음'}")
    logger.info(f"Dry-run: {args.dry_run}")
    logger.info("="*80)

    # 후보 문서 찾기
    candidates = find_ocr_candidates(
        db_path=args.db,
        threshold=args.threshold,
        limit=args.limit
    )

    if not candidates:
        logger.info("OCR이 필요한 문서가 없습니다.")
        return 0

    logger.info(f"OCR 필요 문서: {len(candidates)}개")
    logger.info("")

    # 처리 통계
    stats = {
        'total': len(candidates),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    # 각 문서 처리
    for i, doc in enumerate(candidates, 1):
        logger.info(f"[{i}/{len(candidates)}] 처리 중: {doc['filename']}")
        logger.info(f"  현재: {doc['text_len']}자 ({doc['avg_per_page']:.0f}자/페이지)")

        # 파일 존재 확인
        pdf_path = Path(doc['path'])
        if not pdf_path.exists():
            logger.warning(f"  ⚠️ 파일 없음: {pdf_path}")
            stats['skipped'] += 1
            continue

        if args.dry_run:
            logger.info(f"  [DRY-RUN] OCR 추출 스킵")
            stats['success'] += 1
            continue

        # OCR 추출
        start_time = time.time()
        ocr_text = ocr_extract_pdf(pdf_path)
        duration = time.time() - start_time

        if not ocr_text:
            logger.error(f"  ❌ OCR 실패")
            stats['failed'] += 1
            continue

        # DB 업데이트
        if update_document_text(doc['id'], ocr_text, args.db, extracted_dir):
            improvement = len(ocr_text) - doc['text_len']
            logger.info(f"  ✅ 성공: {len(ocr_text)}자 (+{improvement}자, {duration:.1f}초)")
            stats['success'] += 1
        else:
            logger.error(f"  ❌ DB 업데이트 실패")
            stats['failed'] += 1

    # 최종 요약
    logger.info("")
    logger.info("="*80)
    logger.info("처리 결과 요약")
    logger.info("="*80)
    logger.info(f"총 문서: {stats['total']}")
    logger.info(f"✅ 성공: {stats['success']}")
    logger.info(f"❌ 실패: {stats['failed']}")
    logger.info(f"⚠️ 스킵: {stats['skipped']}")

    if not args.dry_run and stats['success'] > 0:
        logger.info("")
        logger.info("🔄 인덱스 재빌드가 필요합니다:")
        logger.info("  .venv/bin/python3 scripts/reindex_atomic.py")

    logger.info("="*80)

    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
