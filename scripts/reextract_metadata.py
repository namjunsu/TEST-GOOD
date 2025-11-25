#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
메타데이터 재추출 스크립트

OCR 텍스트는 그대로 두고, 메타데이터 필드만 개선된 정규식으로 재추출합니다.
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def extract_metadata(raw_text: str) -> dict:
    """개선된 정규식으로 메타데이터 추출"""
    korean_fields = {}

    # 시행일자 추출
    action_date_match = re.search(
        r"시행일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s*~\s*\d{4}[-./]\d{1,2}[-./]\d{1,2})?)",
        raw_text,
    )
    if action_date_match:
        korean_fields["시행일자"] = action_date_match.group(1)

    # 기안일자 추출
    draft_date_match = re.search(
        r"기안일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{2})?)", raw_text
    )
    if draft_date_match:
        korean_fields["기안일자"] = draft_date_match.group(1)

    # 작성일자 추출
    created_date_match = re.search(r"작성일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2})", raw_text)
    if created_date_match:
        korean_fields["작성일자"] = created_date_match.group(1)

    # 기안자 추출 (개선된 패턴: 공백, 탭, ㅣ, | 허용)
    drafter_match = re.search(r"기안자[\s\|ㅣ]+([가-힣]{2,4})", raw_text)
    if drafter_match:
        korean_fields["기안자"] = drafter_match.group(1)

    # 기안부서 추출
    dept_match = re.search(r"기안부서\s+([^\n]+)", raw_text)
    if dept_match:
        korean_fields["기안부서"] = dept_match.group(1).strip()

    return korean_fields


def find_docs_without_drafter(db_path: str = "metadata.db"):
    """기안자 필드가 비어있는 문서 목록 반환"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        """
        SELECT id, filename, path, text_preview
        FROM documents
        WHERE (drafter IS NULL OR drafter = '')
        AND text_preview LIKE '%기안자%'
        ORDER BY filename ASC
        """
    )
    results = cursor.fetchall()
    conn.close()
    return results


def update_document_metadata(db_path: str, doc_id: int, metadata: dict):
    """DB의 문서 메타데이터 업데이트"""
    conn = sqlite3.connect(db_path)

    # 업데이트할 필드 준비
    updates = []
    params = []

    if "기안자" in metadata:
        updates.append("drafter = ?")
        params.append(metadata["기안자"])

    if not updates:
        conn.close()
        return 0

    # WHERE 조건용 파라미터 추가
    params.append(doc_id)

    # UPDATE 쿼리 실행
    query = f"UPDATE documents SET {', '.join(updates)} WHERE id = ?"
    conn.execute(query, params)

    conn.commit()
    rows_affected = conn.total_changes
    conn.close()

    return rows_affected


def main():
    parser = argparse.ArgumentParser(description="메타데이터 재추출 (OCR 텍스트는 그대로 유지)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 처리 없이 목록만 출력",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리할 최대 문서 수",
    )
    args = parser.parse_args()

    print("🔍 기안자 필드 누락 문서 검색 중...")
    docs = find_docs_without_drafter()

    if not docs:
        print("✅ 기안자 필드가 비어있는 문서 없음")
        return

    print(f"\n📊 발견된 문서: {len(docs)}개")
    print("=" * 80)

    docs_to_process = docs[: args.limit] if args.limit else docs

    # 목록 출력
    for i, (doc_id, filename, path, text_preview) in enumerate(docs_to_process, 1):
        # 텍스트에서 기안자 부분만 추출해서 미리보기
        context_match = re.search(r".{0,20}기안자.{0,30}", text_preview)
        context = context_match.group(0) if context_match else "N/A"

        print(f"{i:3d}. {filename}")
        print(f"     ID: {doc_id}")
        print(f"     컨텍스트: {context}")

    print("=" * 80)

    if args.dry_run:
        print("\n🔵 Dry-run 모드: 실제 처리하지 않음")
        print(f"📝 재추출 예정: {len(docs_to_process)}개 문서")
        return

    # 실제 메타데이터 재추출
    print(f"\n🔄 메타데이터 재추출 시작...")

    success_count = 0
    fail_count = 0

    for i, (doc_id, filename, path, text_preview) in enumerate(docs_to_process, 1):
        print(f"\n[{i}/{len(docs_to_process)}] {filename}")

        # 메타데이터 추출
        metadata = extract_metadata(text_preview)

        if "기안자" not in metadata:
            logger.warning(f"메타데이터 추출 실패: {filename}")
            fail_count += 1
            continue

        # DB 업데이트
        rows_affected = update_document_metadata("metadata.db", doc_id, metadata)
        if rows_affected > 0:
            print(f"   ✓ 기안자: {metadata.get('기안자', 'N/A')}")
            success_count += 1
        else:
            logger.warning(f"DB 업데이트 실패: {filename}")
            fail_count += 1

    print("\n" + "=" * 80)
    print(f"✅ 메타데이터 재추출 완료!")
    print(f"   성공: {success_count}개")
    print(f"   실패: {fail_count}개")

    # 재검증
    print("\n📊 재검증 중...")
    docs_after = find_docs_without_drafter()
    improved = len(docs) - len(docs_after)

    print(f"   이전: {len(docs)}개 누락")
    print(f"   이후: {len(docs_after)}개 누락")
    print(f"   개선: {improved}개 ({improved * 100 / len(docs):.1f}%)")


if __name__ == "__main__":
    main()
