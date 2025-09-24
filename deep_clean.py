#!/usr/bin/env python3
"""
심층 정리 스크립트
==================
실제로 사용하는 파일만 남기고 정리
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

def deep_clean():
    """불필요한 파일 모두 정리"""

    # 실제로 사용하는 파일들만
    KEEP_FILES = {
        # 핵심 시스템
        'web_interface.py',
        'perfect_rag.py',
        'auto_indexer.py',
        'config.py',
        'log_system.py',
        'response_formatter.py',
        'smart_search_enhancer.py',

        # Docker/설정
        'docker-compose.yml',
        'Dockerfile',
        '.env',
        '.env.production',
        'requirements_updated.txt',  # 실제 사용하는 것

        # 문서
        'README.md',
        'README_CLEAN.md',
        'CLAUDE.md',
        'SYSTEM_SPECS.md',
        'SYSTEM_STATUS.md',

        # 정리 스크립트
        'organize_project.py',
        'deep_clean.py'
    }

    # 사용하지 않는 파일들 archive로 이동
    archive_unused = Path('archive/unused')
    archive_unused.mkdir(parents=True, exist_ok=True)

    # 모든 Python 파일 확인
    all_py_files = list(Path('.').glob('*.py'))
    all_txt_files = list(Path('.').glob('*.txt'))
    all_md_files = list(Path('.').glob('*.md'))
    all_yml_files = list(Path('.').glob('*.yml')) + list(Path('.').glob('*.yaml'))

    moved_count = 0

    print("🧹 사용하지 않는 파일 정리 중...")
    print("="*50)

    # Python 파일 정리
    print("\n📝 Python 파일 정리:")
    for file in all_py_files:
        if file.name not in KEEP_FILES:
            dest = archive_unused / file.name
            shutil.move(str(file), str(dest))
            print(f"  ➡️  {file.name} → archive/unused/")
            moved_count += 1

    # requirements 파일 정리
    print("\n📦 Requirements 파일 정리:")
    for file in all_txt_files:
        if 'requirement' in file.name.lower() and file.name != 'requirements_updated.txt':
            dest = archive_unused / file.name
            shutil.move(str(file), str(dest))
            print(f"  ➡️  {file.name} → archive/unused/")
            moved_count += 1

    # 기타 설정 파일 정리
    print("\n⚙️  기타 파일 정리:")
    other_files = [
        'performance_config.yaml',
        'grafana.ini',
        'prometheus.yml',
        'streamlit.log',
        'perfect_rag.log',
        'api_startup.log'
    ]

    for filename in other_files:
        file = Path(filename)
        if file.exists() and filename not in KEEP_FILES:
            if filename.endswith('.log'):
                dest = Path('logs') / filename
            else:
                dest = archive_unused / filename

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(dest))
            print(f"  ➡️  {filename} → {dest.parent}/")
            moved_count += 1

    print(f"\n✅ {moved_count}개 파일 정리 완료")

    # 현재 상태 보고
    print("\n" + "="*50)
    print("📊 최종 프로젝트 상태")
    print("="*50)

    # 루트 파일 카운트
    py_count = len(list(Path('.').glob('*.py')))
    txt_count = len(list(Path('.').glob('*.txt')))
    md_count = len(list(Path('.').glob('*.md')))

    print(f"""
✅ 루트 폴더 (깔끔함):
  • Python 파일: {py_count}개 (핵심만)
  • 설정 파일: {txt_count + 2}개 (.env 포함)
  • 문서: {md_count}개

📁 폴더 구조:
  • docs/ - PDF 문서
  • rag_system/ - RAG 모듈
  • archive/unused/ - 사용 안하는 파일 {moved_count}개
  • logs/ - 로그 파일
  • models/ - AI 모델
    """)

    # requirements 통합
    print("\n📦 Requirements 정리:")
    print("  • requirements_updated.txt - 실제 사용 (이것만 사용!)")
    print("  • 나머지는 archive/unused/로 이동됨")

    return True

def create_final_readme():
    """최종 README 생성"""

    content = """# 🎯 AI-CHAT RAG System

## 🚀 실행 방법 (간단!)

```bash
# Docker로 실행 (권장)
docker compose up

# 또는 로컬 실행
streamlit run web_interface.py
```

## 📁 파일 설명 (이것만 있으면 됨!)

### 핵심 파일 7개:
- `web_interface.py` - 웹 UI
- `perfect_rag.py` - 검색 엔진
- `auto_indexer.py` - 자동 인덱싱
- `config.py` - 설정
- `log_system.py` - 로깅
- `response_formatter.py` - 응답 포맷
- `smart_search_enhancer.py` - 검색 개선

### 설정 파일:
- `requirements_updated.txt` - **이것만 사용!**
- `.env` - 환경 변수
- `docker-compose.yml` - Docker 설정

## ❌ 제거된 것들:
- Asset/장비 검색 (완전 제거)
- 복잡한 추가 시스템들
- 중복 requirements 파일들
- 사용 안하는 Python 파일 30개+

## ✅ 남은 기능:
- PDF 문서 검색
- Qwen2.5 AI 답변
- 자동 인덱싱
- 캐싱 시스템

---
*깔끔하게 정리 완료!*
"""

    with open('README_FINAL.md', 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n✅ README_FINAL.md 생성 완료")

if __name__ == "__main__":
    print("🚀 심층 정리 시작...")
    if deep_clean():
        create_final_readme()
        print("\n🎉 완벽하게 정리되었습니다!")
        print("이제 필요한 파일만 남았습니다!")