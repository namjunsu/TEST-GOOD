#!/usr/bin/env python3
"""
추출된 텍스트에서 불필요한 URL과 노이즈를 제거하는 스크립트
"""

import re
import sys
from pathlib import Path
from typing import List

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def clean_text(text: str) -> str:
    """텍스트에서 노이즈 제거"""

    # 원본 텍스트 백업
    original_text = text

    # STEP 1: 중복 콘텐츠 제거 (마커 제거 전에 먼저 수행!)
    # "[OCR 추출 텍스트]" 이후 모든 내용 삭제
    ocr_marker_patterns = [
        '\n[OCR 추출 텍스트]\n',
        '\n[OCR 추출 텍스트]',
        '[OCR 추출 텍스트]\n',
        '[OCR 추출 텍스트]',
    ]

    for marker in ocr_marker_patterns:
        ocr_marker_idx = text.find(marker)
        if ocr_marker_idx != -1:
            text = text[:ocr_marker_idx]
            logger.debug(f"[OCR 추출 텍스트] 이후 중복 콘텐츠 제거 ({len(original_text) - len(text)}자)")
            break

    # STEP 2: 개별 패턴 제거
    patterns_to_remove = [
        # 그룹웨어 URL 전체 라인 제거
        r'.*gw\.channela-mt\.com/groupware/approval/.*\n?',
        r'.*http://gw\.channela-mt\.com.*\n?',

        # elmarket URL 라인 제거
        r'.*http://www\.elmarket\.co\.kr.*\n?',

        # 페이지 번호 패턴 (예: 1/2, 2/5 등)
        r'^\s*\d+/\d+\s*$\n',

        # URL 잔재 제거 (mode=getPrint 등)
        r'.*mode=getPrint.*\n?',
        r'.*menu_depth=\d+.*\n?',
        r'.*is_mark=.*\n?',
        r'.*idx=\d+.*\n?',

        # OCR 중복 마커 제거
        r'^\[페이지 \d+\]\s*\n',
        r'^\[OCR 추출 텍스트\]\s*\n',
        r'^\[OCR 페이지 \d+\]\s*\n',

        # 빈 줄이 3개 이상 연속되면 2개로 축소
        r'\n{4,}',

        # 줄 끝 공백 제거
        r'[ \t]+$',

        # 파일 시작과 끝의 빈 줄 제거는 나중에
    ]

    # 패턴별로 제거
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)

    # 연속된 빈 줄을 2개로 제한
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 시작과 끝 공백 제거
    text = text.strip()

    # 텍스트가 너무 짧아지면 원본 유지
    if len(text) < 50 and len(original_text) > 100:
        logger.warning(f"텍스트가 너무 짧아짐. 원본 유지: {len(original_text)}자 -> {len(text)}자")
        return original_text

    return text


def process_files(dry_run: bool = False):
    """모든 추출 파일 처리"""

    extracted_dir = Path("data/extracted")
    if not extracted_dir.exists():
        logger.error(f"디렉토리 없음: {extracted_dir}")
        return

    # 모든 txt 파일 찾기
    txt_files = list(extracted_dir.glob("*.txt"))
    logger.info(f"총 {len(txt_files)}개 텍스트 파일 발견")

    # MetadataDB 연결
    db = MetadataDB()

    # 통계
    processed = 0
    modified = 0
    error_count = 0
    total_removed_chars = 0

    for txt_file in txt_files:
        try:
            # 파일 읽기
            with txt_file.open('r', encoding='utf-8') as f:
                original_text = f.read()

            # 텍스트 정리
            cleaned_text = clean_text(original_text)

            # 변경사항이 있는지 확인
            if cleaned_text != original_text:
                removed_chars = len(original_text) - len(cleaned_text)
                total_removed_chars += removed_chars

                logger.info(f"[{txt_file.name}] {len(original_text)}자 -> {len(cleaned_text)}자 (제거: {removed_chars}자)")

                if not dry_run:
                    # 파일 저장
                    with txt_file.open('w', encoding='utf-8') as f:
                        f.write(cleaned_text)

                    # DB 업데이트 (PDF 파일명 기준)
                    pdf_filename = txt_file.name.replace('.txt', '.pdf')
                    doc = db.get_by_filename(pdf_filename)
                    if doc:
                        db.update_text_preview(doc['path'], cleaned_text)
                        logger.debug(f"  DB 업데이트: {doc['path']}")

                modified += 1

            processed += 1

            # 진행 상황 표시
            if processed % 50 == 0:
                logger.info(f"진행: {processed}/{len(txt_files)} 파일 처리")

        except Exception as e:
            logger.error(f"오류 발생: {txt_file.name}: {e}")
            error_count += 1
            continue

    # 결과 요약
    logger.info("\n" + "="*80)
    logger.info("텍스트 정리 완료")
    logger.info("="*80)
    logger.info(f"총 파일: {len(txt_files)}개")
    logger.info(f"처리 완료: {processed}개")
    logger.info(f"수정됨: {modified}개")
    logger.info(f"오류: {error_count}개")
    logger.info(f"총 제거된 문자: {total_removed_chars:,}자")
    logger.info(f"평균 제거: {total_removed_chars // modified if modified > 0 else 0}자/파일")

    if dry_run:
        logger.info("\n[DRY RUN] 실제 파일은 수정되지 않았습니다")
    else:
        logger.info("\n✅ 파일 정리 완료. BM25 인덱스 재구축이 필요합니다:")
        logger.info("   .venv/bin/python3 scripts/reindex_atomic.py")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='추출 텍스트 노이즈 제거')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션만 실행')
    args = parser.parse_args()

    process_files(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())