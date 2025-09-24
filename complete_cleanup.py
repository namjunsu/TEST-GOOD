#!/usr/bin/env python3
"""
완전 정리 스크립트
==================
모든 불필요한 파일 한번에 정리
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

def complete_cleanup():
    """모든 파일 완전 정리"""

    # 정리할 디렉토리 생성
    dirs = [
        'archive/scripts',
        'archive/logs',
        'archive/configs',
        'archive/reports',
        'archive/misc'
    ]

    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    # 정리할 파일들
    to_move = {
        # Shell 스크립트들
        'deploy.sh': 'archive/scripts',
        'deploy_optimized.sh': 'archive/scripts',
        'docker_start.sh': 'archive/scripts',
        'monitor.sh': 'archive/scripts',
        'organize_folders.sh': 'archive/scripts',
        'quick_start.sh': 'archive/scripts',
        'remove_duplicates.sh': 'archive/scripts',
        'restart_system.sh': 'archive/scripts',
        'restore_backup.sh': 'archive/scripts',
        'run_all_services.sh': 'archive/scripts',
        'setup_autostart.sh': 'archive/scripts',
        'start_system.sh': 'archive/scripts',
        'cleanup.sh': 'archive/scripts',
        'check_status.sh': 'archive/scripts',
        'get-docker.sh': 'archive/scripts',

        # 로그 파일들
        'metadata_build.log': 'archive/logs',
        'ocr_full.log': 'archive/logs',
        'ocr_processing.log': 'archive/logs',
        'streamlit.log': 'archive/logs',
        'api_startup.log': 'archive/logs',

        # 테스트 결과들
        'real_test_results.txt': 'archive/reports',
        'test_results.json': 'archive/reports',
        'technical_team_test_results.json': 'archive/reports',
        'quality_report_20250915_063405.json': 'archive/reports',
        'quality_report_20250915_063457.json': 'archive/reports',
        'quality_report_20250915_063649.json': 'archive/reports',
        'real_quality_report_20250915_084107.json': 'archive/reports',

        # 설정 파일들
        'config.yaml': 'archive/configs',
        'improved_settings.json': 'archive/configs',
        'pytest.ini': 'archive/configs',

        # 메타데이터/백업
        'document_metadata.json': 'archive/misc',
        'document_metadata.backup': 'archive/misc',

        # 로고/이미지 (유지할지 확인)
        # 'channel_a_logo_inverted.png': 유지
        # 'logo_inverted.png': 유지
    }

    moved = 0
    errors = []

    print("🧹 완전 정리 시작...")
    print("="*50)

    for file, dest in to_move.items():
        if Path(file).exists():
            try:
                dest_path = Path(dest) / file
                shutil.move(file, str(dest_path))
                print(f"  ✅ {file} → {dest}/")
                moved += 1
            except Exception as e:
                errors.append(f"{file}: {e}")

    # 캐시 폴더들 정리
    cache_dirs = ['__pycache__', '.pytest_cache', 'cache']
    for d in cache_dirs:
        if Path(d).exists():
            try:
                if d == '__pycache__':
                    shutil.rmtree(d)
                    print(f"  🗑️  {d} 삭제")
                else:
                    shutil.move(d, f'archive/misc/{d}')
                    print(f"  ✅ {d} → archive/misc/")
                moved += 1
            except Exception as e:
                errors.append(f"{d}: {e}")

    if errors:
        print(f"\n⚠️  오류 발생:")
        for e in errors:
            print(f"  • {e}")

    print(f"\n✅ {moved}개 항목 정리 완료")

    # 최종 상태
    show_final_state()

def show_final_state():
    """최종 상태 표시"""

    print("\n" + "="*50)
    print("📊 최종 프로젝트 상태")
    print("="*50)

    # 루트 파일 카운트
    all_files = list(Path('.').glob('*'))
    py_files = [f for f in all_files if f.suffix == '.py']
    md_files = [f for f in all_files if f.suffix == '.md']
    yml_files = [f for f in all_files if f.suffix in ['.yml', '.yaml']]
    txt_files = [f for f in all_files if f.suffix == '.txt']

    print(f"""
✅ 루트 디렉토리 (깨끗함!):
  • Python 파일: {len(py_files)}개
  • 문서 파일: {len(md_files)}개
  • 설정 파일: {len(yml_files) + len(txt_files) + 2}개 (.env 포함)
  • 이미지: 2개 (로고)

📁 정리된 구조:
  • docs/ - PDF 문서들
  • rag_system/ - RAG 모듈
  • models/ - AI 모델
  • logs/ - 현재 로그
  • archive/ - 보관 파일
    - scripts/ - Shell 스크립트
    - logs/ - 오래된 로그
    - configs/ - 오래된 설정
    - reports/ - 테스트 보고서
    - misc/ - 기타

🎯 사용하는 파일만 남음:
  • 핵심 Python 7개
  • Docker 설정
  • README 문서
  • 로고 파일
    """)

if __name__ == "__main__":
    complete_cleanup()
    print("\n🎉 완벽하게 정리되었습니다!")