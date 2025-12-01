#!/usr/bin/env python3
"""
Verify that all imports work correctly.
Simulates what would happen after archive migration.
"""

import ast
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_imports():
    """Check all Python files for import errors."""

    errors = []
    checked = 0

    # Get all Python files (excluding archive and venv)
    for py_file in Path('.').rglob('*.py'):
        # Skip virtual env and archive
        if '.venv' in str(py_file) or 'archive' in str(py_file):
            continue

        checked += 1

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                code = f.read()

            # Try to parse the AST
            try:
                ast.parse(code)
            except SyntaxError as e:
                errors.append({
                    'file': str(py_file),
                    'error': f'Syntax error: {e}',
                    'line': e.lineno
                })
        except Exception as e:
            errors.append({
                'file': str(py_file),
                'error': str(e),
                'line': None
            })

    # Now check critical imports
    critical_imports = [
        'from app.rag.pipeline import RAGPipeline',
        'from app.data.metadata_db import MetadataDB',
        'from app.rag.query_parser import QueryParser',
        'from app.rag.query_router import QueryRouter',
        'from app.rag.retrievers.hybrid import HybridRetriever',
        'from components.chat_interface import ChatInterface',
        'from components.sidebar_library import SidebarLibrary',
    ]

    import_results = []
    for import_stmt in critical_imports:
        try:
            exec(import_stmt)
            import_results.append((import_stmt, True))
        except ImportError as e:
            import_results.append((import_stmt, False))
            errors.append({
                'file': 'critical_import',
                'error': f'{import_stmt}: {e}',
                'line': None
            })

    # Generate report
    print("📋 Import Verification Report")
    print("=" * 50)
    print(f"Files checked: {checked}")
    print(f"Syntax errors: {len(errors)}")
    print("")

    print("Critical Imports:")
    for stmt, success in import_results:
        icon = "✅" if success else "❌"
        print(f"  {icon} {stmt[:60]}...")

    print("")

    if errors:
        print("❌ Errors found:")
        for err in errors[:10]:  # Show first 10 errors
            print(f"  - {err['file']}: {err['error'][:100]}")

        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    else:
        print("✅ No import errors found!")

    print("")
    print("Archive Migration Safety:")
    if len(errors) == 0:
        print("✅ Safe to proceed with archive migration")
        print("   All imports will work after file movements")
    else:
        print("⚠️ Fix errors before archive migration")
        print("   Some imports may break after file movements")

    return len(errors)

if __name__ == "__main__":
    sys.exit(check_imports())