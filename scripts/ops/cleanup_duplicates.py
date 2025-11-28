#!/usr/bin/env python3
"""
중복 파일 자동 정리 스크립트

year_정보 없 폴더의 중복 파일을 삭제합니다.
DB에 이미 등록된 문서만 안전하게 삭제합니다.
"""

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def get_file_hash(file_path: Path) -> str:
    """파일 해시 계산"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:8]


def get_db_files(db_path: str = "metadata.db") -> set:
    """DB에 등록된 파일 경로 목록"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT path FROM documents")
    paths = {row[0] for row in cursor.fetchall()}
    conn.close()
    return paths


def find_year_from_filename(filename: str) -> str:
    """파일명에서 연도 추출"""
    import re

    match = re.match(r"(\d{4})-", filename)
    if match:
        return match.group(1)
    return None


def main():
    parser = argparse.ArgumentParser(description="중복 파일 자동 정리")
    parser.add_argument(
        "--dry-run", action="store_true", help="실제 삭제 없이 목록만 출력"
    )
    args = parser.parse_args()

    duplicate_dir = Path("docs/year_정보 없")
    if not duplicate_dir.exists():
        print("✅ year_정보 없 폴더가 없습니다 (중복 없음)")
        return

    # DB에 등록된 파일 목록
    db_files = get_db_files()

    # 중복 파일 찾기
    duplicates = []
    for pdf_file in duplicate_dir.glob("*.pdf"):
        # 연도별 폴더에 동일 파일명이 있는지 확인
        year = find_year_from_filename(pdf_file.name)
        if year:
            year_file = Path(f"docs/year_{year}") / pdf_file.name
            if year_file.exists():
                # 파일 해시 비교
                if get_file_hash(pdf_file) == get_file_hash(year_file):
                    # DB에 등록되어 있는지 확인
                    if str(year_file) in db_files:
                        duplicates.append((pdf_file, year_file))

    if not duplicates:
        print("✅ 중복 파일 없음")
        return

    print(f"\n📊 발견된 중복 파일: {len(duplicates)}개")
    print("=" * 80)

    for i, (dup_file, original_file) in enumerate(duplicates, 1):
        print(f"{i:3d}. {dup_file.name}")
        print(f"     원본: {original_file}")
        print(f"     중복: {dup_file}")

    print("=" * 80)

    if args.dry_run:
        print("\n🔵 Dry-run 모드: 실제 삭제하지 않음")
        print(f"📝 삭제 예정: {len(duplicates)}개 파일")
        return

    # 실제 삭제
    print("\n🗑️  중복 파일 삭제 시작...")

    deleted_count = 0
    for dup_file, original_file in duplicates:
        try:
            dup_file.unlink()
            logger.info(f"삭제: {dup_file.name}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"삭제 실패: {dup_file.name} - {e}")

    print(f"\n✅ 중복 파일 삭제 완료: {deleted_count}개")

    # year_정보 없 폴더가 비었으면 삭제
    remaining = list(duplicate_dir.glob("*.pdf"))
    if not remaining:
        duplicate_dir.rmdir()
        print("✅ year_정보 없 폴더 삭제 완료 (비어있음)")
    else:
        print(f"⚠️  year_정보 없 폴더에 {len(remaining)}개 파일 남음 (수동 확인 필요)")


if __name__ == "__main__":
    main()
