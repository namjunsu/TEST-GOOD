#!/usr/bin/env python3
"""
DB에 없는 문서를 찾아서 다시 incoming으로 이동시키는 복구 스크립트

processed/year_* 폴더의 PDF 중 metadata.db에 없는 것을 찾아서
docs/incoming으로 다시 이동시켜 재처리할 수 있게 합니다.
"""

import sqlite3
import shutil
from pathlib import Path
import sys

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_files_in_db():
    """DB에 있는 파일명 목록 반환"""
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM documents")
    files_in_db = {row[0] for row in cursor.fetchall()}
    conn.close()
    return files_in_db

def find_missing_files():
    """processed/year_* 폴더에서 DB에 없는 파일 찾기"""
    missing_files = []

    # DB에 있는 파일 목록
    files_in_db = get_files_in_db()
    print(f"DB에 등록된 문서: {len(files_in_db)}개")

    # processed와 year_* 폴더 스캔
    search_dirs = [
        Path("docs/processed"),
        *Path("docs").glob("year_*")
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        for pdf_file in search_dir.glob("*.pdf"):
            if pdf_file.name not in files_in_db:
                missing_files.append(pdf_file)
                print(f"  ❌ DB에 없음: {pdf_file}")

    return missing_files

def recover_missing_files(missing_files):
    """DB에 없는 파일들을 incoming으로 이동"""
    incoming_dir = Path("docs/incoming")
    incoming_dir.mkdir(exist_ok=True)

    recovered_count = 0
    for pdf_file in missing_files:
        try:
            dest = incoming_dir / pdf_file.name
            if dest.exists():
                print(f"  ⚠️  이미 incoming에 존재: {pdf_file.name}")
                continue

            shutil.move(str(pdf_file), str(dest))
            print(f"  ✅ 복구: {pdf_file} → {dest}")
            recovered_count += 1
        except Exception as e:
            print(f"  ❌ 복구 실패: {pdf_file} - {e}")

    return recovered_count

def main():
    print("=" * 60)
    print("📦 DB에 없는 문서 복구 스크립트")
    print("=" * 60)

    # 1. DB에 없는 파일 찾기
    print("\n1. DB에 없는 파일 검색 중...")
    missing_files = find_missing_files()

    if not missing_files:
        print("\n✅ 모든 파일이 DB에 정상 등록되어 있습니다.")
        return

    print(f"\n⚠️  DB에 없는 파일: {len(missing_files)}개")

    # 2. 파일 목록 표시
    print("\n복구할 파일:")

    # 처음 10개만 표시
    for i, f in enumerate(missing_files[:10]):
        print(f"  - {f.name}")
    if len(missing_files) > 10:
        print(f"  ... 외 {len(missing_files)-10}개")

    # 자동 진행 (사용자 입력 없이)
    print("\n자동으로 복구를 진행합니다...")

    # 3. 복구 실행
    print("\n2. 파일 복구 중...")
    recovered = recover_missing_files(missing_files)

    # 4. 결과 출력
    print("\n" + "=" * 60)
    print("📊 복구 완료")
    print("=" * 60)
    print(f"✅ 복구된 파일: {recovered}개")
    print(f"📁 위치: docs/incoming/")
    print("\n다음 명령어로 재처리하세요:")
    print("  ./add_document.sh")
    print("=" * 60)

if __name__ == "__main__":
    main()