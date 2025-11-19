#!/usr/bin/env python3
"""
Usage Audit Script
코드 및 스크립트 사용/미사용 판정 (휴리스틱 기반)
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path.cwd().resolve()
REPORTS_DIR = PROJECT_ROOT / "reports"


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def find_python_files() -> list[str]:
    """모든 Python 파일 찾기 (venv/노이즈 디렉터리 제외)."""
    files: list[str] = []
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "archive"}

    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        # 디렉터리 필터링
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

        for fname in filenames:
            if fname.endswith(".py"):
                p = Path(root) / fname
                files.append(str(p.relative_to(PROJECT_ROOT)))

    return sorted(files)


def has_rg() -> bool:
    """ripgrep 존재 여부."""
    return shutil.which("rg") is not None


def search_imports_with_rg(stem: str) -> list[Path]:
    """
    rg로 import 사용 흔적 검색.
    - 단순 휴리스틱: 'import ...<stem>' 이 포함된 .py 파일
    """
    try:
        result = subprocess.run(
            ["rg", "-l", f"import.*{stem}", "--type", "py"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=5,
        )
        if result.returncode not in (0, 1):  # 0: found, 1: not found
            return []

        stdout = result.stdout.strip()
        if not stdout:
            return []

        return [Path(line.strip()) for line in stdout.splitlines() if line.strip()]
    except Exception:
        return []


def check_file_usage(rel_path: str, rg_available: bool) -> dict:
    """단일 파일 사용 여부 판정 (휴리스틱)."""
    path = PROJECT_ROOT / rel_path
    stem = path.stem

    # 1. import 참조 검색
    imported_in: list[str] = []
    if rg_available:
        hits = search_imports_with_rg(stem)
        for hit in hits:
            # 자기 자신 제외
            if hit.resolve() != path.resolve():
                imported_in.append(str(hit))

    # 2. CLI 엔트리 포인트 검사
    is_cli = False
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if 'if __name__ == "__main__"' in text:
            is_cli = True
    except Exception:
        # 읽기 실패 시 CLI 판단은 포기
        is_cli = False

    # 3. 특수 파일 검사 (파일 이름 기준)
    special_names = {
        "__init__.py",
        "conftest.py",
        "setup.py",
        "web_interface.py",
        # start_ai_chat.sh 는 .py 대상이 아니므로 제외
    }
    is_special = path.name in special_names

    status = "USED" if (imported_in or is_cli or is_special) else "UNUSED"

    return {
        "filepath": rel_path,
        "imported_in": imported_in,
        "import_count": len(imported_in),
        "is_cli": is_cli,
        "is_special": is_special,
        "status": status,
    }


def main() -> None:
    print("=" * 80)
    print("📊 USAGE AUDIT - Code Asset Analysis")
    print("=" * 80)
    print(f"Project root: {PROJECT_ROOT}")
    print()

    ensure_reports_dir()

    py_files = find_python_files()
    total_files = len(py_files)
    print(f"Found {total_files} Python files\n")

    rg_available = has_rg()
    if not rg_available:
        print(
            "⚠️  ripgrep(rg)이 설치되어 있지 않습니다. import 기반 사용성 분석은 비활성화됩니다."
        )
        print("    → status=UNUSED 판정은 신뢰도가 낮을 수 있습니다.\n")

    results: list[dict] = []
    unused: list[dict] = []
    used: list[dict] = []

    print("Analyzing usage...")
    for rel in py_files:
        result = check_file_usage(rel, rg_available)
        results.append(result)

        if result["status"] == "UNUSED":
            unused.append(result)
        else:
            used.append(result)

    print(f"  Used: {len(used)}")
    print(f"  Unused (suspected): {len(unused)}")
    print()

    # JSON 저장
    raw_path = REPORTS_DIR / "usage_audit_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Markdown 리포트 생성
    md_path = REPORTS_DIR / "USAGE_AUDIT.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Usage Audit Report\n\n")
        f.write(f"**Date**: {now_str}\n\n")
        f.write(f"**Project Root**: `{PROJECT_ROOT}`\n\n")
        f.write(f"**Total Files**: {total_files}\n")
        f.write(f"**Used**: {len(used)}\n")
        f.write(f"**Unused (suspected)**: {len(unused)}\n\n")
        if not rg_available:
            f.write("> ⚠️ ripgrep(rg) 미설치 상태. UNUSED 판정 신뢰도 낮음.\n\n")

        f.write("## Unused Files (suspected)\n\n")
        f.write("| File | Status | Reason |\n")
        f.write("|------|--------|--------|\n")
        for item in sorted(unused, key=lambda x: x["filepath"]):
            f.write(
                f"| `{item['filepath']}` | UNUSED | "
                f"No imports (rg={rg_available}), not CLI, not special |\n"
            )

        f.write("\n## Used Files (top 20 by import count)\n\n")
        f.write("| File | Imports | CLI | Special |\n")
        f.write("|------|---------|-----|---------|\n")
        for item in sorted(used, key=lambda x: -x["import_count"])[:20]:
            cli = "✓" if item["is_cli"] else ""
            special = "✓" if item["is_special"] else ""
            f.write(
                f"| `{item['filepath']}` | {item['import_count']} | {cli} | {special} |\n"
            )

    print("✅ Reports saved:")
    print(f"  - {raw_path}")
    print(f"  - {md_path}\n")

    # Summary
    print("=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    if total_files > 0:
        used_ratio = len(used) / total_files * 100
        unused_ratio = len(unused) / total_files * 100
    else:
        used_ratio = unused_ratio = 0.0

    print(f"Total Python files: {total_files}")
    print(f"Used files: {len(used)} ({used_ratio:.1f}%)")
    print(f"Unused files (suspected): {len(unused)} ({unused_ratio:.1f}%)")
    print()

    if unused:
        print("⚠️ Top 10 unused (suspected) files:")
        for item in unused[:10]:
            print(f"  - {item['filepath']}")


if __name__ == "__main__":
    main()
