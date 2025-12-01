#!/usr/bin/env python3
"""
파일 시스템 vs 메타데이터 DB 동기화 상태 확인

사용법:
    python scripts/check_fs_vs_db.py
    python scripts/check_fs_vs_db.py --year 2025
    python scripts/check_fs_vs_db.py --fix  # 자동 수정 (주의!)
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Set, Dict, List

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_filesystem_files(year: str = None) -> Dict[str, Set[str]]:
    """파일 시스템에서 PDF 파일 목록 가져오기

    Returns:
        {year: set of filenames}
    """
    docs_dir = Path("docs")
    result = {}

    # year_* 폴더 스캔
    for year_dir in sorted(docs_dir.glob("year_*")):
        if not year_dir.is_dir():
            continue

        dir_year = year_dir.name.replace("year_", "")

        # 특정 연도만 필터링
        if year and dir_year != year:
            continue

        pdf_files = set()
        for pdf_file in year_dir.glob("*.pdf"):
            pdf_files.add(pdf_file.name)

        result[dir_year] = pdf_files

    return result


def get_db_files(year: str = None) -> Dict[str, Set[str]]:
    """메타데이터 DB에서 문서 목록 가져오기

    Returns:
        {year: set of filenames}
    """
    conn = sqlite3.connect("metadata.db")
    cursor = conn.cursor()

    if year:
        cursor.execute(
            "SELECT year, filename FROM documents WHERE year = ?",
            (year,)
        )
    else:
        cursor.execute("SELECT year, filename FROM documents WHERE year != ''")

    result = {}
    for row in cursor.fetchall():
        doc_year = row[0]
        filename = row[1]

        if doc_year not in result:
            result[doc_year] = set()
        result[doc_year].add(filename)

    conn.close()
    return result


def compare_sync(fs_files: Dict[str, Set[str]], db_files: Dict[str, Set[str]]) -> Dict:
    """동기화 상태 비교"""
    all_years = sorted(set(fs_files.keys()) | set(db_files.keys()))

    issues = {
        "summary": {
            "total_years": len(all_years),
            "synced_years": 0,
            "years_with_issues": 0
        },
        "details": {}
    }

    for year in all_years:
        fs_set = fs_files.get(year, set())
        db_set = db_files.get(year, set())

        only_in_fs = fs_set - db_set  # 파일은 있는데 DB에 없음
        only_in_db = db_set - fs_set  # DB에는 있는데 파일 없음
        synced = fs_set & db_set

        is_synced = len(only_in_fs) == 0 and len(only_in_db) == 0

        if is_synced:
            issues["summary"]["synced_years"] += 1
        else:
            issues["summary"]["years_with_issues"] += 1

        issues["details"][year] = {
            "synced": is_synced,
            "fs_count": len(fs_set),
            "db_count": len(db_set),
            "synced_count": len(synced),
            "only_in_fs": sorted(only_in_fs),
            "only_in_db": sorted(only_in_db)
        }

    return issues


def print_report(issues: Dict):
    """리포트 출력"""
    print("=" * 80)
    print("📊 파일 시스템 vs 메타데이터 DB 동기화 상태")
    print("=" * 80)
    print()

    summary = issues["summary"]
    print(f"총 연도: {summary['total_years']}")
    print(f"✅ 동기화됨: {summary['synced_years']}")
    print(f"⚠️  문제 있음: {summary['years_with_issues']}")
    print()

    if summary['years_with_issues'] == 0:
        print("🎉 모든 연도가 완벽하게 동기화되어 있습니다!")
        return

    print("=" * 80)
    print("📋 연도별 상세 현황")
    print("=" * 80)
    print()

    for year, detail in sorted(issues["details"].items()):
        if detail["synced"]:
            print(f"✅ {year}년: {detail['synced_count']}개 문서 (동기화됨)")
        else:
            print(f"⚠️  {year}년:")
            print(f"   파일 시스템: {detail['fs_count']}개")
            print(f"   DB: {detail['db_count']}개")
            print(f"   동기화: {detail['synced_count']}개")

            if detail["only_in_fs"]:
                print(f"   📁 파일만 있음 (DB 누락): {len(detail['only_in_fs'])}개")
                for filename in detail["only_in_fs"][:5]:
                    print(f"      - {filename}")
                if len(detail["only_in_fs"]) > 5:
                    print(f"      ... 외 {len(detail['only_in_fs']) - 5}개")

            if detail["only_in_db"]:
                print(f"   💾 DB만 있음 (파일 누락): {len(detail['only_in_db'])}개")
                for filename in detail["only_in_db"][:5]:
                    print(f"      - {filename}")
                if len(detail["only_in_db"]) > 5:
                    print(f"      ... 외 {len(detail['only_in_db']) - 5}개")

            print()


def main():
    parser = argparse.ArgumentParser(description="파일 시스템 vs DB 동기화 확인")
    parser.add_argument("--year", help="특정 연도만 확인 (예: 2025)")
    parser.add_argument("--fix", action="store_true", help="자동 수정 (미구현)")

    args = parser.parse_args()

    if args.fix:
        print("❌ 자동 수정 기능은 아직 구현되지 않았습니다.")
        print("수동으로 수정하거나 scripts/ingest_from_docs.py를 사용하세요.")
        sys.exit(1)

    print("📂 파일 시스템 스캔 중...")
    fs_files = get_filesystem_files(args.year)

    print("💾 메타데이터 DB 조회 중...")
    db_files = get_db_files(args.year)

    print("🔍 동기화 상태 비교 중...")
    issues = compare_sync(fs_files, db_files)

    print()
    print_report(issues)

    # Exit code: 0 if synced, 1 if issues
    if issues["summary"]["years_with_issues"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
