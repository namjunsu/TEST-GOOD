#!/usr/bin/env python3
"""
Usage Audit Script
코드 및 스크립트 사용/미사용 판정
"""
import os
import re
import subprocess
from pathlib import Path
from collections import defaultdict
import json


def find_python_files():
    """모든 Python 파일 찾기"""
    files = []
    for root, dirs, filenames in os.walk("."):
        # Skip venv, node_modules, etc
        dirs[:] = [d for d in dirs if d not in ['.venv', 'venv', 'node_modules', '.git', '__pycache__']]

        for fname in filenames:
            if fname.endswith('.py'):
                files.append(os.path.join(root, fname))

    return files


def check_file_usage(filepath):
    """파일의 사용 여부 확인"""
    # 1. Import 체크 (다른 파일에서 import 되는지)
    module_name = filepath.replace('./', '').replace('/', '.').replace('.py', '')

    # ripgrep으로 참조 검색
    try:
        result = subprocess.run(
            ['rg', '-l', f'import.*{Path(filepath).stem}', '--type', 'py'],
            capture_output=True,
            text=True,
            timeout=5
        )
        imported_in = result.stdout.strip().split('\n') if result.stdout.strip() else []
        # 자기 자신 제외
        imported_in = [f for f in imported_in if f != filepath]
    except:
        imported_in = []

    # 2. CLI 엔트리포인트 체크
    is_cli = False
    if 'if __name__ == "__main__"' in open(filepath).read():
        is_cli = True

    # 3. 특수 파일 체크
    special_files = ['__init__.py', 'conftest.py', 'setup.py', 'web_interface.py', 'start_ai_chat.sh']
    is_special = any(s in filepath for s in special_files)

    return {
        'filepath': filepath,
        'imported_in': imported_in,
        'import_count': len(imported_in),
        'is_cli': is_cli,
        'is_special': is_special,
        'status': 'USED' if (imported_in or is_cli or is_special) else 'UNUSED'
    }


def main():
    print("=" * 80)
    print("📊 USAGE AUDIT - Code Asset Analysis")
    print("=" * 80)
    print()

    py_files = find_python_files()
    print(f"Found {len(py_files)} Python files")
    print()

    results = []
    unused = []
    used = []

    print("Analyzing usage...")
    for fpath in py_files:
        result = check_file_usage(fpath)
        results.append(result)

        if result['status'] == 'UNUSED':
            unused.append(result)
        else:
            used.append(result)

    print(f"  Used: {len(used)}")
    print(f"  Unused: {len(unused)}")
    print()

    # Save results
    with open('reports/usage_audit_raw.json', 'w') as f:
        json.dump(results, f, indent=2)

    # Generate markdown report
    with open('reports/USAGE_AUDIT.md', 'w') as f:
        f.write("# Usage Audit Report\\n\\n")
        f.write(f"**Date**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")
        f.write(f"**Total Files**: {len(py_files)}\\n")
        f.write(f"**Used**: {len(used)}\\n")
        f.write(f"**Unused (suspected)**: {len(unused)}\\n\\n")

        f.write("## Unused Files\\n\\n")
        f.write("| File | Status | Reason |\\n")
        f.write("|------|--------|--------|\\n")

        for item in sorted(unused, key=lambda x: x['filepath']):
            f.write(f"| `{item['filepath']}` | UNUSED | No imports, not CLI, not special |\\n")

        f.write("\\n## Used Files (sample)\\n\\n")
        f.write("| File | Imports | CLI | Special |\\n")
        f.write("|------|---------|-----|---------|\\n")

        for item in sorted(used, key=lambda x: -x['import_count'])[:20]:
            cli = "✓" if item['is_cli'] else ""
            special = "✓" if item['is_special'] else ""
            f.write(f"| `{item['filepath']}` | {item['import_count']} | {cli} | {special} |\\n")

    print("✅ Reports saved:")
    print("  - reports/usage_audit_raw.json")
    print("  - reports/USAGE_AUDIT.md")
    print()

    # Summary
    print("=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    print(f"Total Python files: {len(py_files)}")
    print(f"Used files: {len(used)} ({len(used)/len(py_files)*100:.1f}%)")
    print(f"Unused files: {len(unused)} ({len(unused)/len(py_files)*100:.1f}%)")
    print()

    if unused:
        print("⚠️ Top 10 unused files:")
        for item in unused[:10]:
            print(f"  - {item['filepath']}")


if __name__ == "__main__":
    main()
