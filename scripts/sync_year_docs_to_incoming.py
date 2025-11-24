#!/usr/bin/env python3
"""
연도 폴더(year_YYYY)에 넣어둔 신규 PDF를
docs/incoming/으로 복사해 주는 동기화 스크립트.

동작 정책 (v2 - DB 기반 중복 체크):
1) docs/year_20XX/*.pdf 전체 스캔
2) metadata.db에 이미 등록된 파일명이면 → 스킵 (순환 복사 방지)
3) 같은 파일명이 docs/processed/ 에 있으면 → 이미 처리된 문서로 보고 스킵
4) 같은 파일명이 docs/rejected/ 에 있으면 → 한 번 이상 시도된 문서로 보고 스킵
5) 같은 파일명이 docs/incoming/ 에 있으면 → 이미 대기 중이므로 스킵
6) 위 조건에 모두 해당하지 않는 PDF만 docs/incoming/ 으로 copy2

즉, "아직 한 번도 처리되지 않은 신규 연도 폴더 문서"만 incoming 으로 들어간다.
"""

from pathlib import Path
import shutil
import sqlite3

BASE_DIR = Path("docs")
YEAR_GLOB = "year_20*"  # year_2020, year_2021, ...
DB_PATH = Path("metadata.db")

PROCESSED_DIR = BASE_DIR / "processed"
REJECTED_DIR = BASE_DIR / "rejected"
INCOMING_DIR = BASE_DIR / "incoming"


def load_registered_filenames() -> set[str]:
    """metadata.db에서 이미 등록된 filename 목록 로드"""
    if not DB_PATH.exists():
        print(f"[WARN] DB 파일 없음: {DB_PATH}, DB 체크 스킵")
        return set()

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT filename, path FROM documents")
        rows = cur.fetchall()
        conn.close()

        registered: set[str] = set()
        for filename, path in rows:
            if filename:
                registered.add(filename)
            if path:
                # path 컬럼에 year_2025/xxx.pdf 형태로 들어가 있으므로
                registered.add(Path(path).name)

        return registered
    except Exception as e:
        print(f"[ERROR] DB 로드 실패: {e}")
        return set()


def collect_names(dir_path: Path) -> set[str]:
    """지정 디렉터리 내 *.pdf 파일명을 집합으로 수집 (디렉터리가 없으면 빈 집합)."""
    if not dir_path.exists():
        return set()
    return {p.name for p in dir_path.glob("*.pdf")}


def main() -> None:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    # DB에서 이미 등록된 파일명 로드
    registered_names = load_registered_filenames()
    print(f"[INFO] DB에 등록된 파일 수: {len(registered_names)}개")

    processed_names = collect_names(PROCESSED_DIR)
    rejected_names = collect_names(REJECTED_DIR)
    incoming_names = collect_names(INCOMING_DIR)

    moved = 0
    scanned = 0
    skipped_db = 0
    skipped_processed = 0
    skipped_rejected = 0
    skipped_incoming = 0

    for year_dir in sorted(BASE_DIR.glob(YEAR_GLOB)):
        if not year_dir.is_dir():
            continue

        for src in sorted(year_dir.glob("*.pdf")):
            scanned += 1
            name = src.name

            # 1) DB에 이미 등록된 문서 (순환 복사 방지)
            if name in registered_names:
                skipped_db += 1
                continue

            # 2) 이미 처리된 문서
            if name in processed_names:
                skipped_processed += 1
                continue

            # 3) 재시도 대상이 아닌 rejected 문서
            if name in rejected_names:
                skipped_rejected += 1
                continue

            # 4) 이미 incoming 에 대기 중인 문서
            if name in incoming_names:
                skipped_incoming += 1
                continue

            dst = INCOMING_DIR / name
            print(f"[SYNC] {src} -> {dst}")
            shutil.copy2(src, dst)
            moved += 1

    print(f"\n[결과 요약]")
    print(f"  스캔한 연도 폴더 내 PDF: {scanned}개")
    print(f"  신규 동기화된 문서: {moved}개")
    print(f"  Skip - DB 등록됨: {skipped_db}개")
    print(f"  Skip - processed: {skipped_processed}개")
    print(f"  Skip - rejected: {skipped_rejected}개")
    print(f"  Skip - incoming 대기: {skipped_incoming}개")
    print(f"  incoming 디렉터리: {INCOMING_DIR.resolve()}")


if __name__ == "__main__":
    main()