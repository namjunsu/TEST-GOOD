#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
텍스트 추출 불량 문서 OCR 재처리

텍스트가 100자 미만인 문서들을 찾아서 OCR로 재처리합니다.

사용법:
    python scripts/reprocess_poor_docs_with_ocr.py           # 자동 실행
    python scripts/reprocess_poor_docs_with_ocr.py --dry-run # 확인만
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from scripts.ingest_from_docs import DocumentIngester

logger = get_logger(__name__)


def find_poor_docs(db_path: str = "metadata.db", threshold: int = 100):
    """텍스트 추출이 불량한 문서 목록 반환

    Args:
        db_path: 데이터베이스 경로
        threshold: 텍스트 길이 임계값 (기본 100자)

    Returns:
        (filename, path, text_length) 튜플 리스트
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        """
        SELECT filename, path, length(text_preview) as text_len
        FROM documents
        WHERE length(text_preview) < ?
        ORDER BY text_len ASC
        """,
        (threshold,),
    )
    results = cursor.fetchall()
    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="텍스트 추출 불량 문서 OCR 재처리")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 처리 없이 목록만 출력",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="텍스트 길이 임계값 (기본: 100자)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리할 최대 문서 수",
    )
    args = parser.parse_args()

    print("🔍 텍스트 추출 불량 문서 검색 중...")
    poor_docs = find_poor_docs(threshold=args.threshold)

    if not poor_docs:
        print(f"✅ 텍스트 길이 {args.threshold}자 미만 문서 없음")
        return

    print(f"\n📊 발견된 불량 문서: {len(poor_docs)}개")
    print("=" * 80)

    # 목록 출력
    for i, (filename, path, text_len) in enumerate(poor_docs, 1):
        if args.limit and i > args.limit:
            print(f"\n... ({len(poor_docs) - args.limit}개 더 있음)")
            break
        print(f"{i:3d}. {filename}")
        print(f"     경로: {path}")
        print(f"     텍스트 길이: {text_len}자")

    print("=" * 80)

    if args.dry_run:
        print("\n🔵 Dry-run 모드: 실제 처리하지 않음")
        print(f"📝 재처리 예정: {min(len(poor_docs), args.limit or 999)}개 문서")
        return

    # 실제 OCR 재처리
    print(f"\n🔄 OCR 재처리 시작... (예상 시간: {len(poor_docs) * 15 // 60}~{len(poor_docs) * 30 // 60}분)")

    # 임시로 incoming 폴더에 복사
    incoming_dir = Path("docs/incoming_ocr_retry")
    incoming_dir.mkdir(exist_ok=True)

    docs_to_process = poor_docs[: args.limit] if args.limit else poor_docs

    # 파일 복사
    import shutil

    for filename, path, _ in docs_to_process:
        src = Path(path)
        if src.exists():
            dst = incoming_dir / filename
            if not dst.exists():
                shutil.copy2(src, dst)
                logger.info(f"복사: {filename}")

    # Ingester로 OCR 처리
    print(f"\n📄 {len(docs_to_process)}개 문서 OCR 재처리 중...")
    ingester = DocumentIngester(
        incoming_dir=str(incoming_dir),
        ocr_mode="force",  # 강제 OCR
        dry_run=False,
    )

    # 처리된 파일은 DB 업데이트 (upsert)
    pdf_files = list(incoming_dir.glob("*.pdf"))
    for pdf_file in pdf_files:
        result = ingester.process_file(pdf_file)
        logger.info(f"처리 결과: {result['status']} - {result['filename']}")

    # 임시 폴더 정리
    print(f"\n🧹 임시 폴더 정리: {incoming_dir}")
    for f in incoming_dir.glob("*"):
        f.unlink()
    incoming_dir.rmdir()

    print("\n✅ OCR 재처리 완료!")
    print("\n📊 재검증 중...")

    # 재검증
    poor_docs_after = find_poor_docs(threshold=args.threshold)
    improved = len(poor_docs) - len(poor_docs_after)

    print(f"   이전: {len(poor_docs)}개 불량")
    print(f"   이후: {len(poor_docs_after)}개 불량")
    print(f"   개선: {improved}개 ({improved * 100 / len(poor_docs):.1f}%)")


if __name__ == "__main__":
    main()
