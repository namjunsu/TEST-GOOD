#!/usr/bin/env python3
"""
부분 재인덱싱 스크립트 - 금액 필드만 재추출
- 이상치 doc_id 목록을 읽어서 금액만 재추출
- amount_parser_v2 사용 (라인아이템 우선 + 상/하한 가드)
- DB 업데이트 (amount 필드만)
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple
import pdfplumber

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.amount_parser_v2 import select_document_amount, validate_amount
from app.core.logging import get_logger

logger = get_logger(__name__)

DB_PATH = Path("/home/wnstn4647/AI-CHAT/metadata.db")
DOCS_ROOT = Path("/home/wnstn4647/AI-CHAT/docs")


def extract_pdf_text(pdf_path: Path, max_pages: int = 10) -> Optional[str]:
    """PDF에서 텍스트 추출 (최대 10페이지)"""
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        return None

    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

                # 테이블도 추출 (금액이 테이블에 있을 수 있음)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            text_parts.append(" ".join(str(cell or "") for cell in row))

        full_text = "\n".join(text_parts)
        logger.debug(f"Extracted {len(full_text)} chars from {pdf_path.name}")
        return full_text

    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {e}")
        return None


def reindex_document_amount(doc_id: str, pdf_path: Path) -> Tuple[Optional[int], bool]:
    """
    단일 문서의 금액 재추출 및 검증
    Returns: (validated_amount, success)
    """
    logger.info(f"Reindexing doc_id={doc_id}, path={pdf_path}")

    # 1) PDF 텍스트 추출
    text = extract_pdf_text(pdf_path)
    if not text:
        logger.warning(f"Failed to extract text from {pdf_path}")
        return None, False

    # 2) 금액 추출 (강화된 파서)
    raw_amount = select_document_amount(doc_id, text, item_hint=pdf_path.name)

    # 3) 검증
    validated_amount, is_valid = validate_amount(raw_amount, context=str(pdf_path))

    if is_valid and validated_amount:
        logger.info(f"✓ Extracted valid amount: ₩{validated_amount:,} for {doc_id}")
        return validated_amount, True
    else:
        logger.warning(f"✗ No valid amount found for {doc_id} (raw={raw_amount})")
        return None, False


def update_amount_in_db(doc_id: int, amount: Optional[int]) -> bool:
    """DB의 amount 필드 업데이트"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
            UPDATE documents
            SET amount = ?
            WHERE id = ?
        """, (amount, doc_id))

        conn.commit()
        rows_affected = cur.rowcount
        conn.close()

        if rows_affected > 0:
            amt_str = f"₩{amount:,}" if amount else "NULL"
            logger.info(f"✓ Updated DB: id={doc_id}, amount={amt_str}")
            return True
        else:
            logger.warning(f"✗ No rows updated for id={doc_id}")
            return False

    except Exception as e:
        logger.error(f"DB update error for id={doc_id}: {e}")
        return False


def load_reindex_targets(target_file: Path) -> List[Tuple[int, str]]:
    """재인덱싱 대상 목록 로드 (id, path)"""
    targets = []
    if not target_file.exists():
        logger.error(f"Target file not found: {target_file}")
        return targets

    with open(target_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('\t')
            if len(parts) >= 2:
                doc_id = int(parts[0].strip())  # ID is integer
                path = parts[1].strip()
                targets.append((doc_id, path))

    logger.info(f"Loaded {len(targets)} reindex targets from {target_file}")
    return targets


def reindex_from_target_file(target_file: Path, limit: Optional[int] = None) -> dict:
    """타겟 파일 기반 재인덱싱"""
    targets = load_reindex_targets(target_file)

    if limit:
        targets = targets[:limit]
        logger.info(f"Processing first {limit} targets (limited)")

    stats = {
        'total': len(targets),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    for i, (doc_id, path) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] Processing {doc_id}...")

        pdf_path = Path(path)
        if not pdf_path.exists():
            # 상대 경로로 시도
            pdf_path = DOCS_ROOT / path
            if not pdf_path.exists():
                logger.warning(f"File not found: {path}")
                stats['skipped'] += 1
                continue

        # 금액 재추출
        amount, success = reindex_document_amount(doc_id, pdf_path)

        if success:
            # DB 업데이트
            if update_amount_in_db(doc_id, amount):
                stats['success'] += 1
            else:
                stats['failed'] += 1
        else:
            # 추출 실패 - NULL로 업데이트 (명시적)
            update_amount_in_db(doc_id, None)
            stats['failed'] += 1

    return stats


def reindex_by_doc_ids(doc_ids: List[int]) -> dict:
    """ID 리스트 기반 재인덱싱"""
    stats = {
        'total': len(doc_ids),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    for i, doc_id in enumerate(doc_ids, 1):
        print(f"\n[{i}/{len(doc_ids)}] Processing ID={doc_id}...")

        # DB에서 path 조회
        cur.execute("SELECT path FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()

        if not row:
            logger.warning(f"ID not found in DB: {doc_id}")
            stats['skipped'] += 1
            continue

        pdf_path = Path(row['path'])
        if not pdf_path.exists():
            logger.warning(f"File not found: {pdf_path}")
            stats['skipped'] += 1
            continue

        # 금액 재추출
        amount, success = reindex_document_amount(str(doc_id), pdf_path)

        if success:
            if update_amount_in_db(doc_id, amount):
                stats['success'] += 1
            else:
                stats['failed'] += 1
        else:
            update_amount_in_db(doc_id, None)
            stats['failed'] += 1

    conn.close()
    return stats


def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="부분 재인덱싱 - 금액 필드만 재추출")
    parser.add_argument('--target-file', type=Path, help="재인덱싱 대상 목록 파일 (doc_id<tab>path)")
    parser.add_argument('--doc-ids', nargs='+', help="재인덱싱 대상 doc_id 직접 지정")
    parser.add_argument('--limit', type=int, help="처리할 최대 문서 수 (테스트용)")
    parser.add_argument('--dry-run', action='store_true', help="DB 업데이트 없이 실행 (테스트)")

    args = parser.parse_args()

    if args.dry_run:
        logger.warning("DRY RUN MODE: DB will not be updated")

    print("="*80)
    print("부분 재인덱싱 시작 - 금액 필드만 재추출")
    print("="*80)

    stats = None

    try:
        if args.target_file:
            # 타겟 파일 기반
            stats = reindex_from_target_file(args.target_file, limit=args.limit)

        elif args.doc_ids:
            # doc_id 직접 지정
            doc_ids = args.doc_ids
            if args.limit:
                doc_ids = doc_ids[:args.limit]
            stats = reindex_by_doc_ids(doc_ids)

        else:
            parser.print_help()
            return 1

        # 결과 출력
        if stats:
            print("\n" + "="*80)
            print("재인덱싱 완료 요약")
            print("="*80)
            print(f"Total processed: {stats['total']}")
            print(f"  ✓ Success: {stats['success']}")
            print(f"  ✗ Failed: {stats['failed']}")
            print(f"  ⊘ Skipped: {stats['skipped']}")
            print("="*80)

            success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"Success rate: {success_rate:.1f}%")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
