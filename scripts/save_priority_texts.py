#!/usr/bin/env python3
"""
최우선 10개 문서 중 텍스트가 충분한 9개의 텍스트를 data/extracted에 저장
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pdfplumber
from app.core.logging import get_logger

logger = get_logger(__name__)

EXTRACTED_DIR = BASE_DIR / "data" / "extracted"

PRIORITY_FILES = [
    "2025-07-17_미러클랩_카메라_삼각대_기술검토서.pdf",
    "2024-11-14_뉴스_스튜디오_지미집_Control_Box_수리_건.pdf",
    "2024-08-13_기술관리팀_방송시스템_소모품_구매_검토서.pdf",
    "2024-03-12_멀티_부조정실_백업_오디오_콘솔_LCD_장애_수리_건.pdf",
    "2023-07-11_멀티_부조정실_비디오_스위쳐_장애_네트워크_스위치_구매_기안서.pdf",
    "2022-06-24_대통령실_영상취재_공용_MNG_장기_리스_건.pdf",
    "2019-09-19_멀티부조정실_Logo_Keyer_Control_Panel_수리.pdf",
    "2019-04-17_채널A플러스_IPTV_전송망_SKBB_재계약_검토_건.pdf",
    "2020-03-30_조선중앙tv_수신_장애_보수_건.pdf",
]


def extract_and_save(pdf_path: Path) -> bool:
    """PDF 텍스트 추출 및 저장"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            text = text.strip()

            if len(text) < 100:
                logger.warning(f"  ⚠️ 텍스트 부족: {len(text)}자")
                return False

            # 저장
            txt_filename = pdf_path.with_suffix(".txt").name
            txt_file = EXTRACTED_DIR / txt_filename

            EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

            with txt_file.open('w', encoding='utf-8') as f:
                f.write(text)

            logger.info(f"  ✅ 저장: {txt_file.name} ({len(text)}자)")
            return True

    except Exception as e:
        logger.error(f"  ❌ 실패: {e}")
        return False


def main():
    logger.info("=" * 80)
    logger.info("최우선 9개 문서 텍스트 저장")
    logger.info("=" * 80)

    docs_dir = BASE_DIR / "docs"
    success = 0
    failed = 0

    for i, filename in enumerate(PRIORITY_FILES, 1):
        logger.info(f"\n[{i}/9] {filename}")

        # 파일 찾기
        pdf_path = None
        for year_dir in sorted(docs_dir.glob("year_*"), reverse=True):
            candidate = year_dir / filename
            if candidate.exists():
                pdf_path = candidate
                break

        if not pdf_path:
            logger.warning(f"  ❌ 파일 없음")
            failed += 1
            continue

        if extract_and_save(pdf_path):
            success += 1
        else:
            failed += 1

    # 요약
    logger.info("\n" + "=" * 80)
    logger.info("📊 결과")
    logger.info("=" * 80)
    logger.info(f"성공: {success}개")
    logger.info(f"실패: {failed}개")

    if success > 0:
        logger.info("\n✅ 다음 단계: python scripts/reindex_atomic.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
