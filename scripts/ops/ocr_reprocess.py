#!/usr/bin/env python3
"""
OCR 재처리 통합 스크립트 (v1.0)

기존 5개 스크립트를 하나로 통합:
- force_ocr_update.py
- reprocess_with_ocr.py
- batch_ocr_zero_chars.py
- reprocess_poor_docs_with_ocr.py
- batch_ocr_from_report.py

사용법:
    # 텍스트 < 100자 문서
    python scripts/ops/ocr_reprocess.py --mode poor --threshold 100

    # 페이지당 평균 < 300자 문서
    python scripts/ops/ocr_reprocess.py --mode average --threshold 300

    # 0자 문서만
    python scripts/ops/ocr_reprocess.py --mode zero

    # 파일 목록에서 읽기
    python scripts/ops/ocr_reprocess.py --mode list --file-list docs/targets.txt

    # Dry-run
    python scripts/ops/ocr_reprocess.py --mode poor --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger
from app.rag.ocr.pipeline import ocr_extract_pdf, update_document_text
from app.rag.ocr.selectors import (
    select_by_avg_per_page,
    select_by_text_length,
    select_from_file_list,
    select_zero_text,
)

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="OCR 재처리 통합 스크립트")
    parser.add_argument(
        "--mode",
        choices=["poor", "average", "zero", "list"],
        required=True,
        help="선택 모드 (poor: text<threshold, average: avg/page<threshold, zero: 0자, list: 파일목록)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="임계값 (poor: 100, average: 300)",
    )
    parser.add_argument(
        "--file-list",
        type=str,
        help="파일 목록 경로 (mode=list 필수)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="최대 처리 개수",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="시뮬레이션만 (실제 OCR/DB 업데이트 안 함)",
    )
    parser.add_argument(
        "--db-path",
        default="metadata.db",
        help="DB 파일 경로 (기본: metadata.db)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="OCR DPI (기본: 300)",
    )
    parser.add_argument(
        "--engine",
        choices=["tesseract", "paddleocr"],
        default="paddleocr",
        help="OCR 엔진 선택 (기본: paddleocr)",
    )

    args = parser.parse_args()

    # 1. 문서 선택
    logger.info(f"OCR 재처리 시작 (mode={args.mode}, threshold={args.threshold}, dry_run={args.dry_run})")

    if args.mode == "poor":
        candidates = select_by_text_length(args.db_path, args.threshold, args.limit)
    elif args.mode == "average":
        candidates = select_by_avg_per_page(args.db_path, args.threshold, args.limit)
    elif args.mode == "zero":
        candidates = select_zero_text(args.db_path, args.limit)
    elif args.mode == "list":
        if not args.file_list:
            logger.error("--file-list 필수 (mode=list)")
            sys.exit(1)
        candidates = select_from_file_list(args.file_list, args.db_path)

    if not candidates:
        logger.info("처리할 문서 없음")
        return

    logger.info(f"총 {len(candidates)}개 문서 선택됨")

    # 2. OCR 처리
    success_count = 0
    fail_count = 0
    docs_root = Path("docs").resolve()

    for i, doc in enumerate(candidates, 1):
        filename = doc["filename"]
        rel_path = doc.get("path", filename)
        pdf_path = docs_root / rel_path

        logger.info(f"[{i}/{len(candidates)}] 처리 중: {filename}")

        if not pdf_path.exists():
            logger.warning(f"  파일 없음: {pdf_path}")
            fail_count += 1
            continue

        try:
            if args.dry_run:
                logger.info(f"  [DRY-RUN] OCR 스킵: {filename}")
                success_count += 1
                continue

            # OCR 실행
            full_text = ocr_extract_pdf(
                pdf_path,
                dpi=args.dpi,
                engine=args.engine,
                progress_callback=lambda page, total: logger.debug(f"    페이지 {page}/{total}"),
            )

            # DB 업데이트
            if update_document_text(args.db_path, filename, full_text):
                success_count += 1
                logger.info(f"  ✅ 성공: {len(full_text):,}자 추출")
            else:
                fail_count += 1
                logger.error("  ❌ DB 업데이트 실패")

        except Exception as e:
            logger.error(f"  ❌ 처리 실패: {e}")
            fail_count += 1

        # 진행 상황 출력
        if i % 10 == 0:
            logger.info(f"진행 상황: {i}/{len(candidates)} (성공={success_count}, 실패={fail_count})")

    # 3. 최종 결과
    logger.info("=" * 80)
    logger.info("OCR 재처리 완료")
    logger.info(f"  총 대상: {len(candidates)}개")
    logger.info(f"  성공: {success_count}개")
    logger.info(f"  실패: {fail_count}개")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
