#!/usr/bin/env python3
"""
AI-CHAT 시스템 정리 스크립트
2025-09-29 작성

이 스크립트는 현재 엉망인 파일 구조를 정리합니다.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

def cleanup_system():
    """시스템 파일 구조 정리"""

    print("="*60)
    print("🧹 AI-CHAT 시스템 정리 시작")
    print("="*60)

    # 1. 백업 디렉토리 생성
    old_backups = Path("old_backups")
    old_backups.mkdir(exist_ok=True)

    # 2. 백업 파일들 이동
    backup_files = [
        "backup_20250926_084434",
        "backup_final_20250926_130345",
        "perfect_rag_backup_20250929_171234.py",
        "archive",
        "unused_files",
        "old_docs"
    ]

    moved_count = 0
    for file in backup_files:
        if Path(file).exists():
            try:
                shutil.move(file, old_backups / file)
                print(f"✅ 이동: {file} → old_backups/")
                moved_count += 1
            except Exception as e:
                print(f"❌ 실패: {file} - {e}")

    # 3. 테스트 파일들 정리
    tests_dir = Path("tests")
    tests_dir.mkdir(exist_ok=True)

    test_files = [
        "test_metadata_integration.py",
        "test_metadata_simple.py",
        "test_other_queries.py",
        "test_performance.py",
        "perfect_rag_with_metadata.py"  # 이것도 테스트 파일
    ]

    for file in test_files:
        if Path(file).exists():
            try:
                shutil.move(file, tests_dir / file)
                print(f"✅ 이동: {file} → tests/")
                moved_count += 1
            except Exception as e:
                print(f"❌ 실패: {file} - {e}")

    # 4. 사용 안되는 파일들 확인
    unused_files = [
        "improved_search.py",  # perfect_rag와 중복
        "quick_index.py",      # 임시 스크립트
        "content_search.py",   # 삭제됨
        "index_builder.py",    # 삭제됨
        "multi_doc_search.py"  # 삭제됨
    ]

    archive_unused = Path("old_backups/unused_2025")
    archive_unused.mkdir(exist_ok=True, parents=True)

    for file in unused_files:
        if Path(file).exists():
            try:
                shutil.move(file, archive_unused / file)
                print(f"✅ 아카이브: {file} → old_backups/unused_2025/")
                moved_count += 1
            except Exception as e:
                print(f"❌ 실패: {file} - {e}")

    # 5. 현재 상태 보고
    print("\n" + "="*60)
    print("📊 정리 결과")
    print("="*60)

    print(f"✅ {moved_count}개 파일 정리 완료")

    # 루트 디렉토리의 Python 파일 개수
    py_files = list(Path(".").glob("*.py"))
    print(f"\n📁 루트 디렉토리 Python 파일: {len(py_files)}개")

    # 핵심 파일들 확인
    core_files = [
        "web_interface.py",
        "perfect_rag.py",
        "config.py",
        "everything_like_search.py",
        "metadata_extractor.py",
        "metadata_db.py",
        "log_system.py",
        "response_formatter.py",
        "auto_indexer.py",
        "enhanced_cache.py",
        "ocr_processor.py"
    ]

    print("\n✨ 핵심 파일들:")
    for file in core_files:
        if Path(file).exists():
            size = Path(file).stat().st_size / 1024
            print(f"  ✓ {file:<30} ({size:>7.1f} KB)")

    # 디렉토리 구조
    print("\n📂 디렉토리 구조:")
    dirs = [
        ("docs", "PDF 문서들"),
        ("rag_system", "RAG 시스템 모듈"),
        ("models", "AI 모델"),
        ("config", "설정 파일"),
        ("logs", "로그 파일"),
        ("cache", "캐시"),
        ("tests", "테스트 파일"),
        ("old_backups", "백업/아카이브")
    ]

    for dir_name, desc in dirs:
        if Path(dir_name).exists():
            # 디렉토리 크기 계산
            total_size = sum(f.stat().st_size for f in Path(dir_name).rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            print(f"  ✓ {dir_name:<15} - {desc:<20} ({size_mb:>8.1f} MB)")

    print("\n✅ 시스템 정리 완료!")
    print("\n💡 권장사항:")
    print("1. old_backups 디렉토리는 확인 후 삭제하세요")
    print("2. perfect_rag.py를 기능별로 분할하는 것을 고려하세요")
    print("3. git에서 old_backups/를 .gitignore에 추가하세요")

if __name__ == "__main__":
    cleanup_system()