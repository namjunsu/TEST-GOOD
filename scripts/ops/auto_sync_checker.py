#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
동기화 체크 및 자동 복구 스크립트

파일시스템과 DB의 동기화 상태를 확인하고 자동으로 복구합니다.
"""

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def get_filesystem_files() -> set:
    """파일시스템의 모든 PDF 파일 경로"""
    year_dirs = [
        "docs/year_2014",
        "docs/year_2015",
        "docs/year_2016",
        "docs/year_2017",
        "docs/year_2018",
        "docs/year_2019",
        "docs/year_2020",
        "docs/year_2021",
        "docs/year_2022",
        "docs/year_2023",
        "docs/year_2024",
        "docs/year_2025",
    ]

    files = set()
    for year_dir in year_dirs:
        year_path = Path(year_dir)
        if year_path.exists():
            files.update(year_path.glob("*.pdf"))
    return files


def get_db_files(db_path: str = "metadata.db") -> dict:
    """DB에 등록된 파일 경로 -> ID 매핑"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT id, path, filename FROM documents")
    files = {Path(row[1]): {"id": row[0], "filename": row[2]} for row in cursor.fetchall()}
    conn.close()
    return files


def process_missing_file(file_path: Path, use_ocr: bool = False) -> bool:
    """누락된 파일을 DB에 추가"""
    try:
        # incoming 폴더로 복사
        import shutil

        incoming_path = Path("docs/incoming") / file_path.name
        shutil.copy2(file_path, incoming_path)

        # ingest 스크립트 실행
        venv_python = Path(".venv/bin/python3")
        cmd = [str(venv_python), "scripts/ingest_from_docs.py"]
        if use_ocr:
            cmd.append("--ocr-mode")
            cmd.append("force")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            logger.info(f"✓ 복구 성공: {file_path.name}")
            return True
        else:
            logger.error(f"✗ 복구 실패: {file_path.name}")
            logger.error(result.stderr)
            return False

    except Exception as e:
        logger.error(f"✗ 처리 실패: {file_path.name} - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="동기화 체크 및 자동 복구")
    parser.add_argument("--dry-run", action="store_true", help="실제 복구 없이 체크만")
    parser.add_argument("--auto-fix", action="store_true", help="자동으로 누락 파일 복구")
    parser.add_argument(
        "--use-ocr",
        action="store_true",
        help="OCR 모드로 처리 (이미지 PDF용)",
    )
    args = parser.parse_args()

    print("🔍 파일시스템 vs DB 동기화 체크 중...")

    # 파일시스템과 DB 비교
    fs_files = get_filesystem_files()
    db_files = get_db_files()

    fs_paths = {f for f in fs_files}
    db_paths = set(db_files.keys())

    # 누락 파일 찾기
    missing_in_db = fs_paths - db_paths
    missing_in_fs = db_paths - fs_paths

    # 결과 출력
    print("\n" + "=" * 80)
    print("📊 동기화 상태")
    print("=" * 80)
    print(f"파일시스템: {len(fs_paths)}개 파일")
    print(f"DB: {len(db_paths)}개 파일")
    print(f"동기화됨: {len(fs_paths & db_paths)}개 파일")

    if missing_in_db:
        print(f"\n⚠️  DB 누락: {len(missing_in_db)}개 파일")
        print("=" * 80)
        for i, file_path in enumerate(sorted(missing_in_db), 1):
            print(f"{i:3d}. {file_path.name}")
            print(f"     경로: {file_path}")

    if missing_in_fs:
        print(f"\n⚠️  파일시스템 누락: {len(missing_in_fs)}개 파일")
        print("=" * 80)
        for i, file_path in enumerate(sorted(missing_in_fs), 1):
            db_info = db_files[file_path]
            print(f"{i:3d}. {db_info['filename']}")
            print(f"     DB ID: {db_info['id']}")
            print(f"     예상 경로: {file_path}")

    print("=" * 80)

    # 자동 복구
    if not missing_in_db and not missing_in_fs:
        print("\n✅ 완벽한 동기화 상태입니다!")
        return

    if args.dry_run:
        print("\n🔵 Dry-run 모드: 실제 복구하지 않음")
        if missing_in_db:
            print(f"📝 복구 가능: {len(missing_in_db)}개 파일")
        if missing_in_fs:
            print(f"⚠️  수동 확인 필요: {len(missing_in_fs)}개 파일 (파일시스템 누락)")
        return

    if not args.auto_fix:
        print("\n💡 자동 복구하려면 --auto-fix 옵션을 사용하세요")
        print("   예: python scripts/auto_sync_checker.py --auto-fix")
        if missing_in_db and any("재난" in str(f) for f in missing_in_db):
            print("\n💡 이미지 PDF는 --use-ocr 옵션도 추가하세요")
            print("   예: python scripts/auto_sync_checker.py --auto-fix --use-ocr")
        return

    # 자동 복구 실행
    if missing_in_db:
        print(f"\n🔧 DB 누락 파일 자동 복구 시작... ({len(missing_in_db)}개)")

        success_count = 0
        fail_count = 0

        for file_path in sorted(missing_in_db):
            print(f"\n처리 중: {file_path.name}")
            if process_missing_file(file_path, use_ocr=args.use_ocr):
                success_count += 1
            else:
                fail_count += 1

        print("\n" + "=" * 80)
        print("📊 복구 결과")
        print("=" * 80)
        print(f"✅ 성공: {success_count}개")
        print(f"❌ 실패: {fail_count}개")

    if missing_in_fs:
        print(f"\n⚠️  파일시스템 누락 {len(missing_in_fs)}개는 수동 확인이 필요합니다")
        print("   (rejected 폴더 또는 백업에서 복원 필요)")


if __name__ == "__main__":
    main()
