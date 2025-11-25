#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
P1: 텍스트 품질 개선 (간소화 버전)
- pdfplumber로 전체 페이지 재추출
- 기존 추출이 부족했던 문서 대상
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pdfplumber
import sqlite3
from app.core.logging import get_logger

logger = get_logger(__name__)

EXTRACTED_DIR = BASE_DIR / "data" / "extracted"


def extract_full_text(pdf_path: Path) -> str:
    """pdfplumber로 전체 페이지 텍스트 추출"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            return text.strip()
    except Exception as e:
        logger.error(f"추출 실패: {pdf_path.name} - {e}")
        return ""


def save_extracted_text(pdf_path: Path, text: str) -> Path:
    """추출된 텍스트 저장"""
    txt_filename = pdf_path.with_suffix(".txt").name
    txt_file = EXTRACTED_DIR / txt_filename

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    with txt_file.open('w', encoding='utf-8') as f:
        f.write(text)

    return txt_file


def get_poor_extraction_files(threshold: int = 100) -> list:
    """DB에서 텍스트가 부족한 문서 목록"""
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
    parser = argparse.ArgumentParser(description='P1: 텍스트 품질 개선 (pdfplumber 전체 재추출)')
    parser.add_argument('--limit', type=int, help='최대 처리 개수')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션만')
    parser.add_argument('--threshold', type=int, default=100, help='텍스트 임계값 (기본: 100자)')
    args = parser.parse_args()

    # 대상 파일
    logger.info(f"텍스트 부족 문서 검색 중 (< {args.threshold}자)")
    poor_files = get_poor_extraction_files(args.threshold)

    if not poor_files:
        logger.info("✅ 처리 대상 없음")
        return 0

    logger.info(f"📋 대상: {len(poor_files)}개")

    if args.limit:
        poor_files = poor_files[:args.limit]
        logger.info(f"   → limit: {len(poor_files)}개만 처리")

    if args.dry_run:
        logger.info("\n[DRY RUN]")
        for i, f in enumerate(poor_files, 1):
            logger.info(f"  {i}. {f['filename']} ({f['text_len']}자)")
        return 0

    # 처리
    stats = {'success': 0, 'failed': 0, 'improved': 0}

    for i, file_info in enumerate(poor_files, 1):
        pdf_path = file_info['path']
        filename = file_info['filename']
        old_len = file_info['text_len']

        logger.info(f"\n[{i}/{len(poor_files)}] {filename} (현재: {old_len}자)")

        if not pdf_path.exists():
            logger.warning(f"  ❌ 파일 없음")
            stats['failed'] += 1
            continue

        text = extract_full_text(pdf_path)

        if text and len(text) >= 50:
            txt_file = save_extracted_text(pdf_path, text)
            new_len = len(text)
            improvement = new_len - old_len

            logger.info(f"  ✅ 저장: {txt_file.name}")
            logger.info(f"     {old_len}자 → {new_len}자 (+{improvement}자)")

            stats['success'] += 1
            if improvement > 0:
                stats['improved'] += 1
        else:
            logger.warning(f"  ⚠️ 추출 실패 또는 부족")
            stats['failed'] += 1

    # 통계
    logger.info("\n" + "=" * 80)
    logger.info("📊 결과")
    logger.info("=" * 80)
    logger.info(f"총 처리: {len(poor_files)}개")
    logger.info(f"  성공: {stats['success']}개")
    logger.info(f"  실패: {stats['failed']}개")
    logger.info(f"  개선: {stats['improved']}개")
    logger.info("=" * 80)

    if stats['improved'] > 0:
        logger.info("\n✅ 다음: python scripts/reindex_atomic.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
