#!/usr/bin/env python3
"""
연도 폴더(year_YYYY)에 넣어둔 신규 PDF를
docs/incoming/으로 복사해 주는 동기화 스크립트.

동작 정책:
1) docs/year_20XX/*.pdf 전체 스캔
2) 같은 파일명이 docs/processed/ 에 있으면 → 이미 처리된 문서로 보고 스킵
3) 같은 파일명이 docs/rejected/ 에 있으면 → 한 번 이상 시도된 문서로 보고 스킵
4) 같은 파일명이 docs/incoming/ 에 있으면 → 이미 대기 중이므로 스킵
5) 위 조건에 모두 해당하지 않는 PDF만 docs/incoming/ 으로 copy2

즉, "아직 한 번도 처리되지 않은 신규 연도 폴더 문서"만 incoming 으로 들어간다.
"""

from pathlib import Path
import shutil

BASE_DIR = Path("docs")
YEAR_GLOB = "year_20*"  # year_2020, year_2021, ...

PROCESSED_DIR = BASE_DIR / "processed"
REJECTED_DIR = BASE_DIR / "rejected"
INCOMING_DIR = BASE_DIR / "incoming"


def collect_names(dir_path: Path) -> set[str]:
    """지정 디렉터리 내 *.pdf 파일명을 집합으로 수집 (디렉터리가 없으면 빈 집합)."""
    if not dir_path.exists():
        return set()
    return {p.name for p in dir_path.glob("*.pdf")}


def main() -> None:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    processed_names = collect_names(PROCESSED_DIR)
    rejected_names = collect_names(REJECTED_DIR)
    incoming_names = collect_names(INCOMING_DIR)

    moved = 0
    scanned = 0

    for year_dir in sorted(BASE_DIR.glob(YEAR_GLOB)):
        if not year_dir.is_dir():
            continue

        for src in sorted(year_dir.glob("*.pdf")):
            scanned += 1
            name = src.name

            # 1) 이미 처리된 문서
            if name in processed_names:
                # print(f"[SKIP] 이미 processed 에 존재: {name}")
                continue

            # 2) 재시도 대상이 아닌 rejected 문서
            if name in rejected_names:
                # print(f"[SKIP] 이미 rejected 에 존재: {name}")
                continue

            # 3) 이미 incoming 에 대기 중인 문서
            if name in incoming_names:
                # print(f"[SKIP] 이미 incoming 에 존재: {name}")
                continue

            dst = INCOMING_DIR / name
            print(f"[SYNC] {src} -> {dst}")
            shutil.copy2(src, dst)
            moved += 1

    print(f"[INFO] 스캔한 연도 폴더 내 PDF: {scanned}개")
    print(f"[INFO] 신규 동기화된 문서: {moved}개")
    print(f"[INFO] incoming 디렉터리: {INCOMING_DIR.resolve()}")


if __name__ == "__main__":
    main()