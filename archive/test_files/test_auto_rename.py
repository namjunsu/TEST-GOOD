#!/usr/bin/env python3
"""
파일명 공백 자동 변환 테스트
"""
from pathlib import Path
import tempfile
import shutil

def test_rename_function():
    """테스트 함수"""
    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test_docs"
        test_dir.mkdir()

        # 테스트 파일 생성 (공백 포함)
        test_files = [
            "2024 구매 문서.pdf",
            "2023 수리 보고서.txt",
            "장비 구매 신청서 2024.pdf",
            "normal_file.pdf",  # 공백 없는 파일
        ]

        for filename in test_files:
            file_path = test_dir / filename
            file_path.write_text("test content")
            print(f"✅ 생성: {filename}")

        # auto_indexer의 rename 함수 테스트
        from auto_indexer import AutoIndexer
        indexer = AutoIndexer(docs_dir=str(test_dir))

        print("\n📝 파일명 변환 테스트:")
        for file_path in test_dir.glob("*"):
            new_path = indexer._rename_file_with_underscore(file_path)
            if file_path != new_path:
                print(f"   변경됨: {file_path.name} → {new_path.name}")
            else:
                print(f"   유지됨: {file_path.name}")

        print("\n📊 최종 파일 목록:")
        for file_path in sorted(test_dir.glob("*")):
            print(f"   - {file_path.name}")

if __name__ == "__main__":
    print("="*50)
    print("🔧 파일명 공백 자동 변환 테스트")
    print("="*50)
    test_rename_function()
    print("\n✅ 테스트 완료!")