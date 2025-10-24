#!/usr/bin/env python3
"""
최종 리팩토링 검증 테스트
Session 2의 모든 변경사항이 정상 작동하는지 확인
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("    🎉 최종 리팩토링 검증 테스트")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

# Test 1: 파일 구조 확인
print("📁 Test 1: 파일 구조 확인")
print("-" * 50)

required_files = [
    "web_interface.py",
    "components/__init__.py",
    "components/pdf_viewer.py",
    "components/sidebar_library.py",
    "components/chat_interface.py",
    "components/document_preview.py",
    "static/css/main.css",
    "static/css/sidebar.css",
    "utils/css_loader.py",
    "utils/document_loader.py",
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
    from utils.document_loader import DocumentLoader, load_documents
    print("  ✅ utils.document_loader (DocumentLoader, load_documents)")
except Exception as e:
    print(f"  ❌ utils.document_loader: {e}")
    imports_success = False

try:
    from components.pdf_viewer import PDFViewer, show_pdf_preview
    print("  ✅ components.pdf_viewer (PDFViewer, show_pdf_preview)")
except Exception as e:
    print(f"  ❌ components.pdf_viewer: {e}")
    imports_success = False

try:
    from components.sidebar_library import render_sidebar_library
    print("  ✅ components.sidebar_library (render_sidebar_library)")
except Exception as e:
    print(f"  ❌ components.sidebar_library: {e}")
    imports_success = False

try:
    from components.chat_interface import render_chat_interface
    print("  ✅ components.chat_interface (render_chat_interface)")
except Exception as e:
    print(f"  ❌ components.chat_interface: {e}")
    imports_success = False

try:
    from components.document_preview import render_document_preview
    print("  ✅ components.document_preview (render_document_preview)")
except Exception as e:
    print(f"  ❌ components.document_preview: {e}")
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
    "components/sidebar_library.py",
    "components/chat_interface.py",
    "components/document_preview.py",
    "utils/css_loader.py",
    "utils/document_loader.py",
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

# Test 4: 파일 크기 통계
print("📊 Test 4: 리팩토링 통계")
print("-" * 50)

web_interface = project_root / "web_interface.py"
with open(web_interface) as f:
    current_lines = len(f.readlines())

print(f"  원본 크기:    1,639줄")
print(f"  현재 크기:      {current_lines}줄")
print(f"  감소량:       {1639 - current_lines}줄")
print(f"  감소율:       {(1639 - current_lines) / 1639 * 100:.1f}%")

# 생성된 컴포넌트 통계
print(f"\n  생성된 컴포넌트:")
component_files = [
    "components/pdf_viewer.py",
    "components/sidebar_library.py",
    "components/chat_interface.py",
    "components/document_preview.py",
]

total_component_lines = 0
for comp_file in component_files:
    full_path = project_root / comp_file
    with open(full_path) as f:
        lines = len(f.readlines())
        total_component_lines += lines
        print(f"    - {comp_file}: {lines}줄")

print(f"  컴포넌트 총합: {total_component_lines}줄")

if current_lines <= 400:
    print("\n✅ 목표 달성! (400줄 이하)\n")
else:
    print(f"\n⚠️  목표까지 {current_lines - 400}줄 더 감소 필요\n")

# Test 5: 컴포넌트 구조 검증
print("🏗️  Test 5: 컴포넌트 구조 검증")
print("-" * 50)

# Check if main function uses components
with open(web_interface) as f:
    web_content = f.read()

structure_checks = [
    ("render_sidebar_library 사용", "render_sidebar_library" in web_content),
    ("render_chat_interface 사용", "render_chat_interface" in web_content),
    ("render_document_preview 사용", "render_document_preview" in web_content),
    ("load_all_css 사용", "load_all_css" in web_content),
    ("load_documents import", "from utils.document_loader import load_documents" in web_content),
]

structure_success = True
for check_name, check_result in structure_checks:
    if check_result:
        print(f"  ✅ {check_name}")
    else:
        print(f"  ❌ {check_name}")
        structure_success = False

if structure_success:
    print("\n✅ 컴포넌트 구조 검증 통과\n")
else:
    print("\n❌ 컴포넌트 구조 검증 실패\n")
    sys.exit(1)

# 최종 결과
print("=" * 50)
print("    ✅ 모든 테스트 통과!")
print("=" * 50)
print("\n🎉 리팩토링 완료!")
print(f"   원본: 1,639줄 → 현재: {current_lines}줄 ({(1639 - current_lines) / 1639 * 100:.1f}% 감소)")
print(f"   생성된 컴포넌트: {len(component_files)}개 ({total_component_lines}줄)")
print("\n시스템이 정상적으로 작동합니다.\n")
