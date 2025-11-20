#!/usr/bin/env python3
"""
P1: 텍스트 품질 개선 스크립트
- 텍스트 누락/부족 문서를 대상으로 OCR 재처리
- poppler 의존성 없이 pytesseract + PIL 사용
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pdfplumber
from PIL import Image
import pytesseract
import sqlite3
from app.core.logging import get_logger

logger = get_logger(__name__)

EXTRACTED_DIR = BASE_DIR / "data" / "extracted"


def extract_text_pdfplumber(pdf_path: Path) -> tuple[str, str]:
    """pdfplumber로 텍스트 추출

    Returns:
        (extracted_text, method) - 추출된 텍스트와 방법
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            return text.strip(), "pdfplumber"
    except Exception as e:
        logger.warning(f"pdfplumber 실패: {pdf_path.name} - {e}")
        return "", "failed"


def extract_text_ocr_PIL(pdf_path: Path, dpi: int = 200) -> tuple[str, str]:
    """PIL + pytesseract로 OCR 처리 (poppler 불필요)

    Returns:
        (extracted_text, method) - 추출된 텍스트와 방법
    """
    try:
        # PDF의 첫 페이지만 이미지로 변환 시도
        # (poppler 없이는 전체 페이지 변환이 어려우므로 pdfplumber + PIL 조합 사용)

        with pdfplumber.open(pdf_path) as pdf:
            ocr_text = ""
            for i, page in enumerate(pdf.pages):
                # 페이지를 이미지로 변환
                try:
                    im = page.to_image(resolution=dpi)
                    # PIL Image로 변환
                    pil_image = im.original

                    # OCR 수행
                    page_text = pytesseract.image_to_string(pil_image, lang='kor+eng')
                    ocr_text += page_text + "\n\n"

                except Exception as e:
                    logger.warning(f"페이지 {i+1} OCR 실패: {e}")
                    continue

            return ocr_text.strip(), "ocr"

    except Exception as e:
        logger.error(f"OCR 실패: {pdf_path.name} - {e}")
        return "", "failed"


def save_extracted_text(pdf_path: Path, text: str) -> Path:
    """추출된 텍스트 저장"""
    txt_filename = pdf_path.with_suffix(".txt").name
    txt_file = EXTRACTED_DIR / txt_filename

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    with txt_file.open('w', encoding='utf-8') as f:
        f.write(text)

    return txt_file


def get_poor_extraction_files(threshold: int = 100) -> list:
    """DB에서 텍스트가 부족한 문서 목록 가져오기"""
    db_path = BASE_DIR / "metadata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT path, filename, length(COALESCE(text_preview, '')) as text_len
        FROM documents
        WHERE text_len < {threshold}
        ORDER BY text_len
    ''')

    files = []
    for row in cursor.fetchall():
        path, filename, text_len = row
        files.append({
            'path': Path(path),
            'filename': filename,
            'text_len': text_len
        })

    conn.close()
    return files


def main():
    parser = argparse.ArgumentParser(description='P1: 텍스트 품질 개선')
    parser.add_argument('--limit', type=int, help='최대 처리 개수')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션만 실행')
    parser.add_argument('--dpi', type=int, default=200, help='OCR DPI (기본: 200)')
    parser.add_argument('--threshold', type=int, default=100, help='텍스트 임계값 (기본: 100자)')
    parser.add_argument('--force-ocr', action='store_true', help='pdfplumber 스킵하고 OCR만 사용')
    args = parser.parse_args()

    # 대상 파일 목록
    logger.info(f"텍스트 부족 문서 검색 중 (임계값: {args.threshold}자)")
    poor_files = get_poor_extraction_files(args.threshold)

    if not poor_files:
        logger.info("✅ 처리 대상 문서 없음")
        return 0

    logger.info(f"📋 처리 대상: {len(poor_files)}개 문서")

    if args.limit:
        poor_files = poor_files[:args.limit]
        logger.info(f"   → limit 적용: {len(poor_files)}개만 처리")

    if args.dry_run:
        logger.info("\n[DRY RUN] 시뮬레이션 모드")
        for i, f in enumerate(poor_files, 1):
            logger.info(f"  {i}. {f['filename']} ({f['text_len']}자)")
        return 0

    # 실제 처리
    stats = {
        'pdfplumber': 0,
        'ocr': 0,
        'failed': 0,
        'improved': 0
    }

    for i, file_info in enumerate(poor_files, 1):
        pdf_path = file_info['path']
        filename = file_info['filename']
        old_len = file_info['text_len']

        logger.info(f"\n[{i}/{len(poor_files)}] {filename} (현재: {old_len}자)")

        if not pdf_path.exists():
            logger.warning(f"  ❌ 파일 없음: {pdf_path}")
            stats['failed'] += 1
            continue

        # 1단계: pdfplumber 시도 (force-ocr 아니면)
        text = ""
        method = ""

        if not args.force_ocr:
            text, method = extract_text_pdfplumber(pdf_path)

        # 2단계: pdfplumber 실패 또는 force-ocr이면 OCR
        if len(text) < args.threshold or args.force_ocr:
            logger.info("  → OCR 처리 시작...")
            text, method = extract_text_ocr_PIL(pdf_path, dpi=args.dpi)

        # 결과 저장
        if text and len(text) >= 50:  # 최소 50자는 있어야 의미있음
            txt_file = save_extracted_text(pdf_path, text)
            new_len = len(text)
            improvement = new_len - old_len

            logger.info(f"  ✅ 저장 완료: {txt_file.name}")
            logger.info(f"     방법: {method}, {old_len}자 → {new_len}자 (+{improvement}자)")

            stats[method] += 1
            if improvement > 0:
                stats['improved'] += 1
        else:
            logger.warning(f"  ⚠️ 추출 실패 또는 텍스트 부족: {method}")
            stats['failed'] += 1

    # 최종 통계
    logger.info("\n" + "=" * 80)
    logger.info("📊 처리 결과")
    logger.info("=" * 80)
    logger.info(f"총 처리: {len(poor_files)}개")
    logger.info(f"  - pdfplumber: {stats['pdfplumber']}개")
    logger.info(f"  - OCR: {stats['ocr']}개")
    logger.info(f"  - 실패: {stats['failed']}개")
    logger.info(f"  - 개선됨: {stats['improved']}개")
    logger.info("=" * 80)

    if stats['improved'] > 0:
        logger.info("\n✅ 다음 단계: 재인덱싱")
        logger.info("   python scripts/reindex_atomic.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
