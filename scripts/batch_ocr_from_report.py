#!/usr/bin/env python3
"""스캔 보고서 기반 일괄 OCR 처리"""

import argparse
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf2image import convert_from_path
import pytesseract
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def read_file_list(report_file: str) -> list:
    """보고서에서 파일 목록 읽기"""
    file_list = []

    with open(report_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # PDF 경로만 추출
            if line.endswith('.pdf') and (line.startswith('/') or line.startswith('docs/')):
                file_list.append(line)

    return file_list


def ocr_pdf(pdf_path: Path, dpi: int = 300) -> str:
    """PDF OCR 처리"""
    try:
        # PDF를 이미지로 변환
        images = convert_from_path(str(pdf_path), dpi=dpi)

        # 각 페이지를 OCR 처리
        ocr_text = ""
        for i, image in enumerate(images, 1):
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
    parser = argparse.ArgumentParser(description='스캔 보고서 기반 일괄 OCR 처리')
    parser.add_argument('--report', default='reports/poor_extraction_files.txt', help='보고서 파일 경로')
    parser.add_argument('--limit', type=int, help='최대 처리 개수')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션만 실행')
    parser.add_argument('--dpi', type=int, default=300, help='OCR DPI (기본: 300)')
    args = parser.parse_args()

    # 보고서에서 파일 목록 읽기
    logger.info(f"보고서 파일 읽기: {args.report}")
    file_paths = read_file_list(args.report)

    if args.limit:
        file_paths = file_paths[:args.limit]

    logger.info(f"\n총 {len(file_paths)}개 파일 OCR 처리 예정")

    if args.dry_run:
        logger.info("\n[DRY RUN] 실제 처리는 수행하지 않습니다\n")
        for idx, path in enumerate(file_paths, 1):
            print(f"{idx}. {Path(path).name}")
        return 0

    # MetadataDB 연결
    db = MetadataDB()

    # 처리 통계
    success_count = 0
    fail_count = 0
    skip_count = 0
    total_chars = 0

    # 각 파일 OCR 처리
    for idx, file_path_str in enumerate(file_paths, 1):
        # 경로 정규화
        pdf_path = Path(file_path_str)
        if not pdf_path.is_absolute():
            # 상대 경로면 절대 경로로 변환
            pdf_path = Path.cwd() / pdf_path

        filename = pdf_path.name

        logger.info(f"\n[{idx}/{len(file_paths)}] {filename}")

        # 파일 존재 확인
        if not pdf_path.exists():
            logger.warning(f"  ⚠️  파일 없음: {pdf_path}")
            fail_count += 1
            continue

        # 이미 처리된 파일인지 확인
        txt_file = Path("data/extracted") / filename.replace('.pdf', '.txt')
        if txt_file.exists():
            txt_size = txt_file.stat().st_size
            if txt_size > 1000:  # 1KB 이상이면 스킵
                logger.info(f"  ⏭️  이미 처리됨: {txt_size}바이트")
                skip_count += 1
                continue

        try:
            # OCR 처리
            start_time = time.time()
            ocr_text = ocr_pdf(pdf_path, dpi=args.dpi)
            elapsed = time.time() - start_time

            if not ocr_text or len(ocr_text) < 50:
                logger.warning(f"  ⚠️  OCR 결과 부족: {len(ocr_text)}자")
                fail_count += 1
                continue

            # 텍스트 파일로 저장
            saved_file = save_extracted_text(filename, ocr_text)

            # MetadataDB 업데이트 (path 사용)
            db.update_text_preview(str(pdf_path), ocr_text)
            logger.info(f"  📊 DB 업데이트: {pdf_path}")

            total_chars += len(ocr_text)
            success_count += 1

            logger.info(f"  ✅ OCR 완료: {len(ocr_text)}자 추출 ({elapsed:.1f}초)")
            logger.info(f"  📝 저장: {saved_file}")

        except Exception as e:
            logger.error(f"  ❌ 실패: {e}")
            fail_count += 1
            continue

    # 결과 요약
    logger.info("\n" + "="*80)
    logger.info("OCR 처리 완료")
    logger.info("="*80)
    logger.info(f"총 처리 대상: {len(file_paths)}개")
    logger.info(f"성공: {success_count}개")
    logger.info(f"실패: {fail_count}개")
    logger.info(f"스킵: {skip_count}개 (이미 처리됨)")
    logger.info(f"총 추출 텍스트: {total_chars:,}자")
    logger.info(f"평균: {total_chars // success_count if success_count > 0 else 0:,}자/파일")

    if success_count > 0:
        logger.info("\n⚠️  BM25 인덱스 재구축이 필요합니다:")
        logger.info("   .venv/bin/python3 scripts/reindex_atomic.py")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
