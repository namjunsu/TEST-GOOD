#!/usr/bin/env python3
"""메타데이터 재추출 스크립트

기존 추출된 텍스트(data/extracted/*.txt)에서 메타데이터를 다시 파싱하여
metadata.db를 업데이트합니다.

OCR 재실행 없이 텍스트 파싱만 수행하므로 빠릅니다.

사용법:
    python scripts/ops/refresh_metadata.py
    python scripts/ops/refresh_metadata.py --dry-run  # 실제 업데이트 없이 확인만
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
DB_PATH = PROJECT_ROOT / "metadata.db"


def extract_drafter(text: str) -> str | None:
    """기안자 추출 (다양한 패턴 지원)

    Args:
        text: OCR 추출된 전체 텍스트

    Returns:
        기안자 이름 또는 None
    """
    # 패턴 1: 기안자 + 다양한 구분자 + 이름
    # 예: "기안자 최새름", "기안자ㅣ윤상현", "기안자     이춘선"
    patterns = [
        r"기안자[\s\|\ㅣ:：\t]+([가-힣]{2,10})",
        r"작성자[\s\|\ㅣ:：\t]+([가-힣]{2,10})",
        r"담당자[\s\|\ㅣ:：\t]+([가-힣]{2,10})",
        r"신청자[\s\|\ㅣ:：\t]+([가-힣]{2,10})",
        r"시행자[\s\|\ㅣ:：\t]+([가-힣]{2,10})",
        # 대표이사 다음 줄에 나오는 이름 (결재란)
        r"대표이사[\s\n]+([가-힣]{2,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            # 불용어 제외 (잘못된 매칭 방지)
            if name not in {"정보", "없음", "기타", "미상", "해당"}:
                return name

    return None


def extract_department(text: str) -> str | None:
    """기안부서 추출

    Args:
        text: OCR 추출된 전체 텍스트

    Returns:
        부서명 또는 None
    """
    patterns = [
        r"기안부서[\s\|\ㅣ:：\t]+([^\n]+)",
        r"소속[\s\|\ㅣ:：\t]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            dept = match.group(1).strip()
            # 너무 긴 경우 자르기
            if len(dept) > 50:
                dept = dept[:50]
            return dept

    return None


def main():
    parser = argparse.ArgumentParser(description="메타데이터 재추출")
    parser.add_argument("--dry-run", action="store_true", help="실제 업데이트 없이 확인만")
    args = parser.parse_args()

    if not EXTRACTED_DIR.exists():
        print(f"❌ 추출 디렉토리 없음: {EXTRACTED_DIR}")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"❌ DB 파일 없음: {DB_PATH}")
        sys.exit(1)

    # Before 통계
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN drafter IS NOT NULL AND drafter != '' AND drafter != '정보 없음' THEN 1 ELSE 0 END) as has_drafter
        FROM documents
    """)
    before_total, before_has = cursor.fetchone()
    before_missing = before_total - before_has

    print("=" * 50)
    print("📊 메타데이터 재추출 시작")
    print("=" * 50)
    print(f"📁 추출 디렉토리: {EXTRACTED_DIR}")
    print(f"💾 DB 경로: {DB_PATH}")
    print(f"🔧 Dry-run: {args.dry_run}")
    print()
    print(f"[Before] 전체: {before_total}건, 기안자 있음: {before_has}건, 없음: {before_missing}건")
    print()

    # 텍스트 파일 처리
    txt_files = list(EXTRACTED_DIR.glob("*.txt"))
    print(f"📄 처리할 텍스트 파일: {len(txt_files)}개")
    print()

    updated_drafter = 0
    updated_dept = 0
    skipped = 0
    not_found = 0

    for i, txt_file in enumerate(txt_files, 1):
        filename = txt_file.stem + ".pdf"

        try:
            text = txt_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  ⚠️ 읽기 실패: {txt_file.name} - {e}")
            continue

        # 기안자 추출
        drafter = extract_drafter(text)
        dept = extract_department(text)

        if drafter or dept:
            if not args.dry_run:
                # 기안자 업데이트 (기존 값이 없거나 "정보 없음"인 경우만)
                if drafter:
                    cursor.execute("""
                        UPDATE documents
                        SET drafter = ?
                        WHERE filename = ?
                        AND (drafter IS NULL OR drafter = '' OR drafter = '정보 없음')
                    """, (drafter, filename))
                    if cursor.rowcount > 0:
                        updated_drafter += 1

                # 부서 업데이트 (컬럼이 있는 경우만)
                # department 컬럼이 없는 DB도 있으므로 skip
                # if dept:
                #     cursor.execute(...)
                pass
            else:
                # Dry-run 모드에서는 DB 조회만
                cursor.execute(
                    "SELECT drafter FROM documents WHERE filename = ?",
                    (filename,)
                )
                row = cursor.fetchone()
                if row:
                    current = row[0]
                    if current in (None, "", "정보 없음") and drafter:
                        updated_drafter += 1
                        if i <= 10:  # 처음 10건만 상세 출력
                            print(f"  📝 {filename}: '{current}' → '{drafter}'")
                else:
                    not_found += 1
        else:
            skipped += 1

        # 진행률 표시
        if i % 100 == 0:
            print(f"  ... {i}/{len(txt_files)} 처리됨")

    if not args.dry_run:
        conn.commit()

    # After 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN drafter IS NOT NULL AND drafter != '' AND drafter != '정보 없음' THEN 1 ELSE 0 END) as has_drafter
        FROM documents
    """)
    after_total, after_has = cursor.fetchone()
    after_missing = after_total - after_has

    conn.close()

    print()
    print("=" * 50)
    print("📊 결과")
    print("=" * 50)
    print(f"✅ 기안자 업데이트: {updated_drafter}건")
    print(f"✅ 부서 업데이트: {updated_dept}건")
    print(f"⏭️ 스킵 (추출 불가): {skipped}건")
    print(f"❓ DB에 없음: {not_found}건")
    print()
    print(f"[Before] 기안자 있음: {before_has}건, 없음: {before_missing}건")
    print(f"[After]  기안자 있음: {after_has}건, 없음: {after_missing}건")
    print(f"[개선]   +{after_has - before_has}건 ({before_missing - after_missing}건 감소)")
    print()

    if args.dry_run:
        print("⚠️ Dry-run 모드: 실제 업데이트되지 않았습니다.")
        print("   실제 업데이트하려면 --dry-run 없이 다시 실행하세요.")


if __name__ == "__main__":
    main()
