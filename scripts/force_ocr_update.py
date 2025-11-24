#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
불량 문서 강제 OCR 재처리 (DB 직접 업데이트)

기존 DB 레코드를 OCR 결과로 덮어씁니다.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def ocr_extract_pdf(pdf_path: Path) -> str:
    """OCR로 PDF 텍스트 추출"""
    try:
        import pytesseract
        from pdf2image import convert_from_path

        logger.info(f"OCR 추출 시작: {pdf_path.name}")

        # PDF → 이미지 변환
        images = convert_from_path(pdf_path, dpi=300)

        # 각 페이지 OCR
        text_pages = []
        for i, image in enumerate(images, 1):
            logger.debug(f"  페이지 {i}/{len(images)} OCR 중...")
            text = pytesseract.image_to_string(image, lang="kor+eng")
            if text.strip():
                text_pages.append(f"[OCR 페이지 {i}]\n{text}")

        full_text = "\n\n".join(text_pages)
        logger.info(f"OCR 완료: {len(full_text)}자 추출")
        return full_text

    except Exception as e:
        logger.error(f"OCR 실패: {pdf_path.name} - {e}")
        return ""


def find_poor_docs(db_path: str = "metadata.db", threshold: int = 100):
    """텍스트 추출이 불량한 문서 목록 반환"""
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


def update_document_text(db_path: str, filename: str, full_text: str):
    """DB의 문서 텍스트 직접 업데이트 (FTS5는 자동 동기화됨)"""
    conn = sqlite3.connect(db_path)
    # text_preview에 전체 텍스트 저장 (FTS5 검색용)
    text_preview = full_text if full_text else ""

    # documents 테이블 업데이트 (FTS5는 content=documents로 자동 동기화)
    conn.execute(
        """
        UPDATE documents
        SET text_preview = ?
        WHERE filename = ?
        """,
        (text_preview, filename),
    )

    conn.commit()
    rows_affected = conn.total_changes
    conn.close()

    logger.info(f"DB 업데이트 완료: {filename} ({len(full_text)}자)")
    return rows_affected


def main():
    parser = argparse.ArgumentParser(description="불량 문서 강제 OCR 재처리")
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

    docs_to_process = poor_docs[: args.limit] if args.limit else poor_docs

    # 목록 출력
    for i, (filename, path, text_len) in enumerate(docs_to_process, 1):
        print(f"{i:3d}. {filename}")
        print(f"     경로: {path}")
        print(f"     텍스트 길이: {text_len}자")

    print("=" * 80)

    if args.dry_run:
        print("\n🔵 Dry-run 모드: 실제 처리하지 않음")
        print(f"📝 재처리 예정: {len(docs_to_process)}개 문서")
        return

    # 실제 OCR 재처리
    print(f"\n🔄 OCR 재처리 시작... (예상 시간: {len(docs_to_process) * 15 // 60}~{len(docs_to_process) * 30 // 60}분)")

    success_count = 0
    fail_count = 0

    for i, (filename, path, text_len) in enumerate(docs_to_process, 1):
        print(f"\n[{i}/{len(docs_to_process)}] {filename}")

        pdf_path = Path(path)
        if not pdf_path.exists():
            logger.error(f"파일 없음: {path}")
            fail_count += 1
            continue

        # OCR 추출
        full_text = ocr_extract_pdf(pdf_path)

        if not full_text or len(full_text) < 100:
            logger.warning(f"OCR 실패 또는 텍스트 부족: {filename} ({len(full_text)}자)")
            fail_count += 1
            continue

        # DB 직접 업데이트
        update_document_text("metadata.db", filename, full_text)
        success_count += 1

    print("\n" + "=" * 80)
    print(f"✅ OCR 재처리 완료!")
    print(f"   성공: {success_count}개")
    print(f"   실패: {fail_count}개")

    # 재검증
    print("\n📊 재검증 중...")
    poor_docs_after = find_poor_docs(threshold=args.threshold)
    improved = len(poor_docs) - len(poor_docs_after)

    print(f"   이전: {len(poor_docs)}개 불량")
    print(f"   이후: {len(poor_docs_after)}개 불량")
    print(f"   개선: {improved}개 ({improved * 100 / len(poor_docs):.1f}%)")


if __name__ == "__main__":
    main()
