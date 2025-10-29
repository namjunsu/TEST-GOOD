#!/usr/bin/env python3
"""
Analyze code usage by tracing imports from entry points.
Identifies used and unused files through dependency analysis.
"""

import ast
import json
import os
from pathlib import Path
from typing import Set, Dict, List
import importlib.util

class ImportTracker:
    def __init__(self):
        self.used_files = set()
        self.import_graph = {}
        self.entry_points = [
            "web_interface.py",
            "app/api/main.py",
            "utils/system_checker.py"
        ]
        self.project_root = Path.cwd()

    def extract_imports(self, file_path: str) -> List[str]:
        """Extract all imports from a Python file."""
        imports = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except:
            pass

        return imports

    def resolve_import_to_file(self, import_name: str, from_file: str) -> List[str]:
        """Resolve an import to actual file paths."""
        resolved = []

        # Handle relative imports
        if import_name.startswith('.'):
            from_dir = Path(from_file).parent
            parts = import_name.lstrip('.').split('.')
            target = from_dir / Path(*parts)
        else:
            # Absolute import
            parts = import_name.split('.')
            target = self.project_root / Path(*parts)

        # Check if it's a file or module
        possibilities = [
            str(target) + '.py',
            str(target / '__init__.py'),
            str(target / '__main__.py')
        ]

        for path in possibilities:
            if os.path.exists(path):
                resolved.append(path)

        # Also check if it's a directory with Python files
        if target.exists() and target.is_dir():
            for py_file in target.glob('**/*.py'):
                resolved.append(str(py_file))

        return resolved

    def trace_dependencies(self, file_path: str, visited: Set[str] = None):
        """Recursively trace all dependencies from a file."""
        if visited is None:
            visited = set()

        if file_path in visited:
            return

        visited.add(file_path)
        self.used_files.add(file_path)

        imports = self.extract_imports(file_path)
        self.import_graph[file_path] = imports

        for imp in imports:
            resolved_files = self.resolve_import_to_file(imp, file_path)
            for resolved in resolved_files:
                self.trace_dependencies(resolved, visited)

    def analyze(self):
        """Perform the full usage analysis."""
        # Trace from all entry points
        for entry in self.entry_points:
            if os.path.exists(entry):
                print(f"Tracing from entry point: {entry}")
                self.trace_dependencies(entry)

        # Find all Python files
        all_py_files = set()
        for root, _, files in os.walk("."):
            # Skip hidden and virtual env directories
            if any(part.startswith('.') or part == '__pycache__' or 'venv' in part
                   for part in Path(root).parts):
                continue

            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    all_py_files.add(file_path.replace('./', ''))

        # Determine unused files
        unused_files = all_py_files - self.used_files

        # Create categorized report
        report = {
            "total_files": len(all_py_files),
            "used_files": len(self.used_files),
            "unused_files": len(unused_files),
            "entry_points": self.entry_points,
            "used": sorted(list(self.used_files)),
            "unused": sorted(list(unused_files)),
            "categories": self.categorize_files(unused_files)
        }

        return report

    def categorize_files(self, files: Set[str]) -> Dict[str, List[str]]:
        """Categorize files by their type/purpose."""
        categories = {
            "tests": [],
            "experiments": [],
            "scripts": [],
            "legacy": [],
            "utils": [],
            "other": []
        }

        for file in files:
            path = Path(file)

            if 'test' in file.lower():
                categories["tests"].append(file)
            elif 'experiment' in file.lower() or 'exp_' in file:
                categories["experiments"].append(file)
            elif file.endswith('.py') and path.parent == Path('.'):
                categories["scripts"].append(file)
            elif 'old' in file.lower() or 'backup' in file.lower() or 'legacy' in file.lower():
                categories["legacy"].append(file)
            elif 'util' in file.lower() or 'helper' in file.lower():
                categories["utils"].append(file)
            else:
                categories["other"].append(file)

        return categories

def main():
    tracker = ImportTracker()
    report = tracker.analyze()

    # Save JSON report
    with open('reports/usage_audit.json', 'w') as f:
        json.dump(report, f, indent=2)

    # Save CSV report for unused files
    with open('reports/dead_code.csv', 'w') as f:
        f.write("file_path,category,lines\n")
        for category, files in report['categories'].items():
            for file in files:
                try:
                    with open(file, 'r', encoding='utf-8') as src:
                        lines = sum(1 for _ in src)
                    f.write(f"{file},{category},{lines}\n")
                except:
                    f.write(f"{file},{category},0\n")

    # Print summary
    print(f"\n📊 Usage Analysis Complete:")
    print(f"  Total Python files: {report['total_files']}")
    print(f"  Used files: {report['used_files']}")
    print(f"  Unused files: {report['unused_files']}")
    print(f"\nUnused by category:")
    for cat, files in report['categories'].items():
        if files:
            print(f"  {cat}: {len(files)} files")

    print(f"\n✅ Reports saved to reports/usage_audit.json and reports/dead_code.csv")

if __name__ == "__main__":
    main()