#!/usr/bin/env python3
"""
프로젝트 폴더 정리 스크립트
========================
모든 파일을 체계적으로 정리
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

def organize_project():
    """프로젝트 정리"""

    # 정리할 폴더 생성
    folders = {
        'archive/old_files': '사용하지 않는 오래된 파일',
        'archive/backups': '백업 파일',
        'archive/test_scripts': '테스트 스크립트',
        'archive/improvements': '개선 시도 파일들',
        'archive/docs': '오래된 문서들',
        'config': '설정 파일',
        'core': '핵심 시스템 파일'
    }

    for folder, desc in folders.items():
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"📁 {folder} - {desc}")

    # 파일 이동 규칙
    move_rules = {
        # 백업 파일들
        'perfect_rag_backup_*.py': 'archive/backups',
        '*_backup_*.py': 'archive/backups',

        # 테스트 파일들
        'test_*.py': 'archive/test_scripts',
        '*_test.py': 'archive/test_scripts',
        'cleanup_code.py': 'archive/test_scripts',
        'clean_perfect_rag.py': 'archive/test_scripts',
        'remove_unused_methods.py': 'archive/test_scripts',

        # 개선 시도 파일들
        'advanced_*.py': 'archive/improvements',
        'auto_backup_system.py': 'archive/improvements',
        'error_handler.py': 'archive/improvements',
        'integrated_system_manager.py': 'archive/improvements',
        'memory_leak_detector.py': 'archive/improvements',
        'realtime_dashboard.py': 'archive/improvements',
        'redis_cache_system.py': 'archive/improvements',
        'smart_assistant.py': 'archive/improvements',
        'system_health_monitor.py': 'archive/improvements',
        'system_integration_test.py': 'archive/improvements',
        'ui_improvements.py': 'archive/improvements',
        'websocket_realtime.py': 'archive/improvements',

        # 오래된 문서들
        'TRANSFORMATION_COMPLETE.md': 'archive/docs',
        'NEXT_LEVEL_COMPLETE.md': 'archive/docs',
        'COMPLETE_SYSTEM.md': 'archive/docs',
        'DEPLOYMENT_COMPLETE.md': 'archive/docs',
        'PRODUCTION_ROADMAP.md': 'archive/docs',
        'OPTIMIZATION_REPORT.md': 'archive/docs',
        'FINAL_OPTIMIZATION_RESULTS.md': 'archive/docs',
        'NEXT_STEPS.md': 'archive/docs',
        'PRACTICAL_SOLUTION.md': 'archive/docs',
        'REFACTORING_GUIDE.md': 'archive/docs',
        'SYSTEM_STATUS_REPORT.md': 'archive/docs',
    }

    # 파일 이동
    moved = 0
    for pattern, destination in move_rules.items():
        files = list(Path('.').glob(pattern))
        for file in files:
            if file.is_file():
                dest_path = Path(destination) / file.name
                try:
                    shutil.move(str(file), str(dest_path))
                    print(f"  ➡️  {file.name} → {destination}")
                    moved += 1
                except Exception as e:
                    print(f"  ❌ {file.name}: {e}")

    print(f"\n✅ {moved}개 파일 이동 완료")

    # 현재 상태 정리
    return analyze_current_state()

def analyze_current_state():
    """현재 폴더 상태 분석"""

    print("\n" + "="*50)
    print("📊 현재 프로젝트 구조")
    print("="*50)

    # 핵심 파일
    core_files = [
        'web_interface.py',
        'perfect_rag.py',
        'auto_indexer.py',
        'config.py',
        'log_system.py',
        'response_formatter.py',
        'smart_search_enhancer.py'
    ]

    # 유틸리티 파일
    utility_files = [
        'memory_optimizer.py',
        'lazy_loader.py',
        'preload_cache.py',
        'performance_optimizer.py',
        'parallel_search_optimizer.py',
        'enable_auto_ocr.py',
        'quick_test.py'
    ]

    # 설정 파일
    config_files = [
        '.env',
        '.env.production',
        'requirements.txt',
        'requirements_updated.txt',
        'docker-compose.yml',
        'Dockerfile',
        'prometheus.yml',
        'grafana.ini'
    ]

    # 문서 파일
    doc_files = [
        'README.md',
        'CLAUDE.md',
        'SYSTEM_SPECS.md',
        'SYSTEM_STATUS.md'
    ]

    print("\n✅ 핵심 시스템 파일 (7개) - 반드시 필요:")
    for f in core_files:
        if Path(f).exists():
            print(f"  • {f}")

    print("\n🔧 유틸리티 파일 (7개) - 성능 최적화용:")
    for f in utility_files:
        if Path(f).exists():
            print(f"  • {f}")

    print("\n⚙️  설정 파일:")
    for f in config_files:
        if Path(f).exists():
            print(f"  • {f}")

    print("\n📚 문서 파일 (유지):")
    for f in doc_files:
        if Path(f).exists():
            print(f"  • {f}")

    # 폴더 구조
    print("\n📁 폴더 구조:")
    folders = [
        'docs/',  # PDF 문서
        'rag_system/',  # RAG 모듈
        'models/',  # AI 모델
        'logs/',  # 로그
        'archive/',  # 보관 파일
        'config/',  # 설정
        '.streamlit/',  # Streamlit 설정
    ]

    for folder in folders:
        if Path(folder).exists():
            count = len(list(Path(folder).glob('**/*')))
            print(f"  • {folder} ({count}개 항목)")

    # 정리 제안
    print("\n" + "="*50)
    print("💡 정리 제안")
    print("="*50)
    print("""
1. **핵심 파일만 루트에 유지**:
   - web_interface.py (메인)
   - perfect_rag.py (엔진)
   - auto_indexer.py (자동 인덱싱)
   - config.py (설정)

2. **archive 폴더로 이동됨**:
   - 모든 테스트 파일
   - 개선 시도 파일들
   - 오래된 문서들
   - 백업 파일들

3. **현재 사용 중인 기능**:
   - 📄 문서 검색 (PDF/TXT)
   - 🔍 하이브리드 검색 (BM25 + Vector)
   - 🤖 Qwen2.5 LLM
   - 💾 캐싱 시스템
   - 📊 자동 인덱싱

4. **제거된 기능**:
   - ❌ Asset/장비 검색 (완전 제거)
   - ❌ 복잡한 추가 시스템들
    """)

if __name__ == "__main__":
    organize_project()
    print("\n✅ 폴더 정리 완료! 깔끔해졌습니다! 🎉")