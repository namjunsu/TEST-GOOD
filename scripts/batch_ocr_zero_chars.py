#!/usr/bin/env python3
"""0자 추출 파일 일괄 OCR 처리"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import List

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf2image import convert_from_path
import pytesseract
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def find_zero_char_files(db_path: str = "metadata.db") -> List[dict]:
    """0자 추출 파일 목록 조회"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 0자 추출 파일 조회
    cursor.execute("""
        SELECT
            id,
            path,
            filename,
            page_count
        FROM documents
        WHERE filename LIKE '%.pdf'
          AND (text_preview IS NULL OR LENGTH(text_preview) = 0)
        ORDER BY filename
    """)

    rows = cursor.fetchall()
    conn.close()

    files = []
    for row in rows:
        files.append({
            'id': row['id'],
            'path': row['path'],
            'filename': row['filename'],
            'page_count': row['page_count']
        })

    return files


def ocr_pdf(pdf_path: Path, dpi: int = 300) -> str:
    """PDF OCR 처리"""
    try:
        # PDF를 이미지로 변환
        images = convert_from_path(str(pdf_path), dpi=dpi)

        # 각 페이지를 OCR 처리
        ocr_text = ""
        for i, image in enumerate(images, 1):
            logger.info(f"  페이지 {i}/{len(images)} OCR 처리 중...")
            page_text = pytesseract.image_to_string(image, lang='kor+eng')
            ocr_text += page_text + "\n\n"

        return ocr_text.strip()

    except Exception as e:
        logger.error(f"OCR 실패: {e}")
        return ""


def save_extracted_text(filename: str, ocr_text: str):
    """추출된 텍스트 저장"""
    output_dir = Path("data/extracted")
    output_dir.mkdir(parents=True, exist_ok=True)

    # PDF 확장자를 txt로 변경
    txt_filename = filename.replace('.pdf', '.txt')
    output_file = output_dir / txt_filename

    with output_file.open('w', encoding='utf-8') as f:
        f.write(ocr_text)

    return output_file


def main():
    parser = argparse.ArgumentParser(description='0자 추출 파일 일괄 OCR 처리')
    parser.add_argument('--limit', type=int, help='최대 처리 개수')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션만 실행')
    parser.add_argument('--dpi', type=int, default=300, help='OCR DPI (기본: 300)')
    args = parser.parse_args()

    # 0자 추출 파일 목록 조회
    logger.info("0자 추출 파일 목록 조회 중...")
    files = find_zero_char_files()

    if args.limit:
        files = files[:args.limit]

    logger.info(f"\n총 {len(files)}개 파일 OCR 처리 예정")

    if args.dry_run:
        logger.info("\n[DRY RUN] 실제 처리는 수행하지 않습니다\n")
        for idx, file_info in enumerate(files, 1):
            print(f"{idx}. {file_info['filename']}")
        return 0

    # MetadataDB 연결
    db = MetadataDB()

    # 처리 통계
    success_count = 0
    fail_count = 0
    total_chars = 0

    # 각 파일 OCR 처리
    for idx, file_info in enumerate(files, 1):
        filename = file_info['filename']
        pdf_path = Path(file_info['path'])

        logger.info(f"\n[{idx}/{len(files)}] {filename}")
        logger.info(f"  경로: {pdf_path}")

        # 파일 존재 확인
        if not pdf_path.exists():
            logger.warning(f"  ⚠️  파일 없음: {pdf_path}")
            fail_count += 1
            continue

        try:
            # OCR 처리
            start_time = time.time()
            ocr_text = ocr_pdf(pdf_path, dpi=args.dpi)
            elapsed = time.time() - start_time

            if not ocr_text:
                logger.warning(f"  ⚠️  OCR 결과 없음")
                fail_count += 1
                continue

            # 텍스트 파일로 저장
            txt_file = save_extracted_text(filename, ocr_text)

            # MetadataDB 업데이트
            db.update_ocr_text(file_info['id'], ocr_text)

            total_chars += len(ocr_text)
            success_count += 1

            logger.info(f"  ✅ OCR 완료: {len(ocr_text)}자 추출 ({elapsed:.1f}초)")
            logger.info(f"  📝 저장: {txt_file}")

        except Exception as e:
            logger.error(f"  ❌ 실패: {e}")
            fail_count += 1
            continue

    # 결과 요약
    logger.info("\n" + "="*80)
    logger.info("OCR 처리 완료")
    logger.info("="*80)
    logger.info(f"총 처리: {len(files)}개")
    logger.info(f"성공: {success_count}개")
    logger.info(f"실패: {fail_count}개")
    logger.info(f"총 추출 텍스트: {total_chars:,}자")
    logger.info(f"평균: {total_chars // success_count if success_count > 0 else 0:,}자/파일")

    if success_count > 0:
        logger.info("\n⚠️  BM25 인덱스 재구축이 필요합니다:")
        logger.info("   .venv/bin/python3 scripts/reindex_atomic.py")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
