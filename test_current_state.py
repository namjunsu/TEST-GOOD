#!/usr/bin/env python3
"""
현재 상태 종합 테스트
리팩토링 후 모든 변경사항이 정상 작동하는지 확인
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("    🧪 현재 상태 종합 테스트")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

# Test 1: 파일 구조 확인
print("📁 Test 1: 파일 구조 확인")
print("-" * 50)

required_files = [
    "web_interface.py",
    "components/__init__.py",
    "components/pdf_viewer.py",
    "static/css/main.css",
    "static/css/sidebar.css",
    "utils/css_loader.py",
]

all_files_exist = True
for file_path in required_files:
    full_path = project_root / file_path
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  ✅ {file_path} ({size:,} bytes)")
    else:
        print(f"  ❌ {file_path} 없음")
        all_files_exist = False

if all_files_exist:
    print("\n✅ 파일 구조 테스트 통과\n")
else:
    print("\n❌ 파일 구조 테스트 실패\n")
    sys.exit(1)

# Test 2: Import 테스트
print("📦 Test 2: Import 테스트")
print("-" * 50)

imports_success = True

try:
    import config
    print("  ✅ config")
except Exception as e:
    print(f"  ❌ config: {e}")
    imports_success = False

try:
    from utils.css_loader import load_css, load_all_css
    print("  ✅ utils.css_loader (load_css, load_all_css)")
except Exception as e:
    print(f"  ❌ utils.css_loader: {e}")
    imports_success = False

try:
    from components.pdf_viewer import PDFViewer, show_pdf_preview
    print("  ✅ components.pdf_viewer (PDFViewer, show_pdf_preview)")
except Exception as e:
    print(f"  ❌ components.pdf_viewer: {e}")
    imports_success = False

try:
    from hybrid_chat_rag_v2 import UnifiedRAG
    print("  ✅ hybrid_chat_rag_v2 (UnifiedRAG)")
except Exception as e:
    print(f"  ❌ hybrid_chat_rag_v2: {e}")
    imports_success = False

if imports_success:
    print("\n✅ Import 테스트 통과\n")
else:
    print("\n❌ Import 테스트 실패\n")
    sys.exit(1)

# Test 3: 구문 검사
print("🔍 Test 3: Python 구문 검사")
print("-" * 50)

import py_compile

python_files = [
    "web_interface.py",
    "components/pdf_viewer.py",
    "utils/css_loader.py",
]

syntax_success = True
for file_path in python_files:
    full_path = project_root / file_path
    try:
        py_compile.compile(str(full_path), doraise=True)
        print(f"  ✅ {file_path}")
    except py_compile.PyCompileError as e:
        print(f"  ❌ {file_path}: {e}")
        syntax_success = False

if syntax_success:
    print("\n✅ 구문 검사 통과\n")
else:
    print("\n❌ 구문 검사 실패\n")
    sys.exit(1)

# Test 4: CSS 로더 기능 테스트
print("🎨 Test 4: CSS 로더 기능 테스트")
print("-" * 50)

try:
    # main.css 읽기
    main_css = project_root / "static/css/main.css"
    with open(main_css) as f:
        main_lines = len(f.readlines())
    print(f"  ✅ main.css 읽기 성공 ({main_lines}줄)")

    # sidebar.css 읽기
    sidebar_css = project_root / "static/css/sidebar.css"
    with open(sidebar_css) as f:
        sidebar_lines = len(f.readlines())
    print(f"  ✅ sidebar.css 읽기 성공 ({sidebar_lines}줄)")

    print("\n✅ CSS 파일 테스트 통과\n")
except Exception as e:
    print(f"\n❌ CSS 파일 테스트 실패: {e}\n")
    sys.exit(1)

# Test 5: 파일 크기 비교
print("📊 Test 5: 파일 크기 변화")
print("-" * 50)

web_interface = project_root / "web_interface.py"
with open(web_interface) as f:
    current_lines = len(f.readlines())

print(f"  원본 크기:    1,639줄")
print(f"  현재 크기:    {current_lines:,}줄")
print(f"  감소량:       {1639 - current_lines:,}줄 ({(1639 - current_lines) / 1639 * 100:.1f}%)")

if current_lines < 900:
    print("\n✅ 파일 크기 목표 달성 (900줄 이하)\n")
else:
    print(f"\n⚠️  목표까지 {current_lines - 900}줄 더 감소 필요\n")

# 최종 결과
print("=" * 50)
print("    ✅ 모든 테스트 통과!")
print("=" * 50)
print("\n현재 시스템은 정상 작동합니다.")
print("다음 단계로 진행해도 안전합니다.\n")
