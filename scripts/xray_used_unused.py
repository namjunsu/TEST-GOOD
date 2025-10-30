#!/usr/bin/env python3
"""
X-Ray analysis to identify used/unused files based on runtime coverage
and entry point reachability analysis.
"""

import ast
import os
import sys
import argparse
import json
import csv
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import xml.etree.ElementTree as ET
from datetime import datetime
import networkx as nx

class XRayAnalyzer:
    """Analyzes codebase to determine used/unused/reachable modules."""

    def __init__(self, roots: List[str], entry_dirs: List[str]):
        self.roots = [Path(r).resolve() for r in roots if Path(r).exists()]
        self.entry_dirs = entry_dirs
        self.base_path = Path.cwd()
        self.modules = {}
        self.coverage_data = {}
        self.reachable_modules = set()
        self.import_graph = nx.DiGraph()

    def load_coverage(self, coverage_xml: str):
        """Load coverage data from XML file."""
        if not Path(coverage_xml).exists():
            print(f"Warning: Coverage file {coverage_xml} not found", file=sys.stderr)
            return

        try:
            tree = ET.parse(coverage_xml)
            root = tree.getroot()

            for package in root.findall('.//package'):
                for cls in package.findall('classes/class'):
                    filename = cls.get('filename')
                    if filename:
                        # Normalize path
                        filepath = Path(filename)
                        if filepath.is_absolute():
                            rel_path = filepath.relative_to(self.base_path)
                        else:
                            rel_path = filepath

                        # Get line coverage
                        lines_covered = 0
                        lines_total = 0
                        for line in cls.findall('lines/line'):
                            lines_total += 1
                            if line.get('hits', '0') != '0':
                                lines_covered += 1

                        coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 0
                        self.coverage_data[str(rel_path)] = {
                            'covered_lines': lines_covered,
                            'total_lines': lines_total,
                            'coverage_percent': coverage_pct
                        }
        except Exception as e:
            print(f"Error loading coverage data: {e}", file=sys.stderr)

    def find_entry_points(self) -> Set[str]:
        """Find all entry point modules."""
        entry_points = set()

        # Check specified entry directories
        for entry_dir in self.entry_dirs:
            entry_path = Path(entry_dir)
            if entry_path.exists():
                for py_file in entry_path.rglob("*.py"):
                    if '__pycache__' not in str(py_file):
                        rel_path = py_file.relative_to(self.base_path)
                        entry_points.add(str(rel_path))

        # Also check for common entry points
        common_entries = [
            'web_interface.py',
            'app/api/main.py',
            'app/main.py',
            'apps/backend.py',
            'apps/ui_app.py'
        ]

        for entry in common_entries:
            if Path(entry).exists():
                entry_points.add(entry)

        # Check for __main__ blocks
        for root in self.roots:
            for py_file in root.rglob("*.py"):
                if '__pycache__' not in str(py_file):
                    try:
                        with open(py_file, 'r', encoding='utf-8') as f:
                            if '__main__' in f.read():
                                rel_path = py_file.relative_to(self.base_path)
                                entry_points.add(str(rel_path))
                    except:
                        pass

        return entry_points

    def build_import_graph(self):
        """Build import dependency graph."""
        for root in self.roots:
            for py_file in root.rglob("*.py"):
                if '__pycache__' not in str(py_file) and 'archive' not in str(py_file):
                    self._analyze_imports(py_file)

    def _analyze_imports(self, filepath: Path):
        """Analyze imports in a Python file."""
        try:
            rel_path = filepath.relative_to(self.base_path)
            module_path = str(rel_path)

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, str(filepath))

            # Extract imports
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)

            # Add to graph
            self.import_graph.add_node(module_path)

            # Try to resolve imports to local modules
            for imp in imports:
                resolved = self._resolve_import(filepath, imp)
                if resolved:
                    self.import_graph.add_edge(module_path, resolved)

        except Exception as e:
            pass  # Silent fail for problematic files

    def _resolve_import(self, from_file: Path, import_name: str) -> Optional[str]:
        """Resolve import to a file path in the codebase."""
        # Try different resolution strategies
        strategies = [
            # Direct file in same directory
            from_file.parent / f"{import_name.split('.')[-1]}.py",
            # Module path from root
            self.base_path / import_name.replace('.', '/') / "__init__.py",
            self.base_path / f"{import_name.replace('.', '/')}.py",
        ]

        # Add app/src specific paths
        for prefix in ['app', 'apps', 'src', 'modules']:
            if import_name.startswith(prefix):
                path = import_name.replace('.', '/')
                strategies.append(self.base_path / f"{path}.py")
                strategies.append(self.base_path / path / "__init__.py")

        for strategy in strategies:
            if strategy.exists():
                try:
                    return str(strategy.relative_to(self.base_path))
                except:
                    pass

        return None

    def find_reachable_modules(self, entry_points: Set[str]) -> Set[str]:
        """Find all modules reachable from entry points."""
        reachable = set()

        for entry in entry_points:
            if entry in self.import_graph:
                # BFS to find all reachable nodes
                visited = set()
                queue = [entry]

                while queue:
                    current = queue.pop(0)
                    if current not in visited:
                        visited.add(current)
                        reachable.add(current)

                        # Add neighbors
                        if current in self.import_graph:
                            for neighbor in self.import_graph.successors(current):
                                if neighbor not in visited:
                                    queue.append(neighbor)

        return reachable

    def classify_modules(self) -> Dict[str, str]:
        """Classify each module as USED, UNUSED, or REACHABLE."""
        classifications = {}

        # Get all Python files
        all_files = set()
        for root in self.roots:
            for py_file in root.rglob("*.py"):
                if '__pycache__' not in str(py_file) and 'archive' not in str(py_file):
                    rel_path = py_file.relative_to(self.base_path)
                    all_files.add(str(rel_path))

        # Find entry points and reachable modules
        entry_points = self.find_entry_points()
        self.build_import_graph()
        reachable = self.find_reachable_modules(entry_points)

        # Classify each file
        for filepath in all_files:
            # Check coverage
            if filepath in self.coverage_data:
                if self.coverage_data[filepath]['coverage_percent'] > 0:
                    classifications[filepath] = 'USED'
                elif filepath in reachable or filepath in entry_points:
                    classifications[filepath] = 'REACHABLE'
                else:
                    classifications[filepath] = 'UNUSED'
            elif filepath in reachable or filepath in entry_points:
                classifications[filepath] = 'REACHABLE'
            else:
                classifications[filepath] = 'UNUSED'

        return classifications

    def generate_file_index(self, classifications: Dict[str, str]) -> str:
        """Generate FILE_INDEX.md content."""
        lines = [
            "# File Index - RAG System X-Ray",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Classification Legend",
            "- **USED**: File has runtime coverage (executed during tests)",
            "- **REACHABLE**: File is imported/reachable from entry points",
            "- **UNUSED**: File has no coverage and is not reachable",
            "",
            "## Directory Tree with Classifications",
            "```",
        ]

        # Build tree structure
        tree = {}
        for filepath, classification in sorted(classifications.items()):
            parts = filepath.split('/')
            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = classification

        # Render tree
        def render_tree(node, indent="", name="", is_file=False):
            result = []
            if is_file:
                tag = node if isinstance(node, str) else 'UNKNOWN'
                badge = {'USED': '✅', 'REACHABLE': '🔗', 'UNUSED': '❌'}.get(tag, '❓')
                result.append(f"{indent}{name} [{badge} {tag}]")
            else:
                if name:
                    result.append(f"{indent}{name}/")
                    indent += "  "

                # Separate files and directories
                files = {k: v for k, v in node.items() if isinstance(v, str)}
                dirs = {k: v for k, v in node.items() if isinstance(v, dict)}

                # Render directories first
                for dir_name in sorted(dirs.keys()):
                    result.extend(render_tree(dirs[dir_name], indent, dir_name))

                # Then files
                for file_name in sorted(files.keys()):
                    result.extend(render_tree(files[file_name], indent, file_name, is_file=True))

            return result

        lines.extend(render_tree(tree))
        lines.append("```")

        # Add summary statistics
        used_count = sum(1 for c in classifications.values() if c == 'USED')
        reachable_count = sum(1 for c in classifications.values() if c == 'REACHABLE')
        unused_count = sum(1 for c in classifications.values() if c == 'UNUSED')

        lines.extend([
            "",
            "## Summary Statistics",
            f"- **Total Python files**: {len(classifications)}",
            f"- **USED (with coverage)**: {used_count} ({used_count/len(classifications)*100:.1f}%)",
            f"- **REACHABLE (no coverage)**: {reachable_count} ({reachable_count/len(classifications)*100:.1f}%)",
            f"- **UNUSED**: {unused_count} ({unused_count/len(classifications)*100:.1f}%)",
        ])

        return "\n".join(lines)

    def generate_module_atlas(self, classifications: Dict[str, str]) -> str:
        """Generate MODULE_ATLAS.md content."""
        lines = [
            "# Module Atlas - RAG System",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Module Details",
            ""
        ]

        # Load metadata if available
        metadata_path = Path("docs/xray/modules_metadata.json")
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                raw_metadata = json.load(f)
                # Convert module paths to file paths
                for module_name, info in raw_metadata.items():
                    if 'path' in info:
                        metadata[info['path']] = info

        for filepath in sorted(classifications.keys()):
            classification = classifications[filepath]
            badge = {'USED': '✅', 'REACHABLE': '🔗', 'UNUSED': '❌'}.get(classification, '❓')

            lines.append(f"### {filepath} [{badge} {classification}]")

            # Add metadata if available
            if filepath in metadata:
                info = metadata[filepath]
                lines.append(f"- **Lines of Code**: {info.get('lines_of_code', 'N/A')}")

                if info.get('docstring'):
                    lines.append(f"- **Module Doc**: {info['docstring'][:100]}...")

                if info.get('entry_point'):
                    lines.append("- **Entry Point**: Yes ⚡")

                # List classes
                if info.get('classes'):
                    lines.append("- **Classes**:")
                    for cls in info['classes'][:5]:  # Limit to 5
                        methods = f"({len(cls.get('methods', []))} methods)" if cls.get('methods') else ""
                        lines.append(f"  - `{cls['name']}` {methods}")

                # List main functions
                if info.get('functions'):
                    lines.append("- **Functions**:")
                    for func in info['functions'][:5]:  # Limit to 5
                        async_tag = " [async]" if func.get('is_async') else ""
                        lines.append(f"  - `{func['name']}({', '.join(func.get('args', [])[:3])}...)`{async_tag}")

            # Add coverage info
            if filepath in self.coverage_data:
                cov = self.coverage_data[filepath]
                lines.append(f"- **Coverage**: {cov['coverage_percent']:.1f}% ({cov['covered_lines']}/{cov['total_lines']} lines)")

            lines.append("")

        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description='X-Ray analysis for used/unused detection')
    parser.add_argument('--roots', nargs='+', default=['src', 'app', 'apps', 'modules'],
                       help='Root directories to analyze')
    parser.add_argument('--coverage', default='reports/xray/coverage.xml',
                       help='Coverage XML file path')
    parser.add_argument('--entry-dirs', nargs='+', default=['apps'],
                       help='Entry point directories')
    parser.add_argument('--index-md', default='docs/xray/FILE_INDEX.md',
                       help='Output path for file index')
    parser.add_argument('--atlas-md', default='docs/xray/MODULE_ATLAS.md',
                       help='Output path for module atlas')
    parser.add_argument('--coverage-csv', default='reports/xray/coverage_map.csv',
                       help='Output path for coverage CSV')
    parser.add_argument('--reachable-list', default='reports/xray/reachable_modules.txt',
                       help='Output path for reachable modules list')

    args = parser.parse_args()

    # Create output directories
    for output_path in [args.index_md, args.atlas_md, args.coverage_csv, args.reachable_list]:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Initialize analyzer
    analyzer = XRayAnalyzer(args.roots, args.entry_dirs)

    # Load coverage data
    print(f"Loading coverage data from {args.coverage}...")
    analyzer.load_coverage(args.coverage)

    # Classify modules
    print("Classifying modules...")
    classifications = analyzer.classify_modules()

    # Generate FILE_INDEX.md
    print(f"Generating {args.index_md}...")
    with open(args.index_md, 'w') as f:
        f.write(analyzer.generate_file_index(classifications))

    # Generate MODULE_ATLAS.md
    print(f"Generating {args.atlas_md}...")
    with open(args.atlas_md, 'w') as f:
        f.write(analyzer.generate_module_atlas(classifications))

    # Generate coverage CSV
    print(f"Generating {args.coverage_csv}...")
    with open(args.coverage_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['File', 'Classification', 'Coverage%', 'Covered Lines', 'Total Lines'])
        for filepath in sorted(classifications.keys()):
            classification = classifications[filepath]
            if filepath in analyzer.coverage_data:
                cov = analyzer.coverage_data[filepath]
                writer.writerow([
                    filepath,
                    classification,
                    f"{cov['coverage_percent']:.1f}",
                    cov['covered_lines'],
                    cov['total_lines']
                ])
            else:
                writer.writerow([filepath, classification, '0.0', 0, 0])

    # Generate reachable modules list
    print(f"Generating {args.reachable_list}...")
    reachable = [f for f, c in classifications.items() if c in ['USED', 'REACHABLE']]
    with open(args.reachable_list, 'w') as f:
        f.write("\n".join(sorted(reachable)))

    # Print summary
    print("\nAnalysis Summary:")
    used = sum(1 for c in classifications.values() if c == 'USED')
    reachable = sum(1 for c in classifications.values() if c == 'REACHABLE')
    unused = sum(1 for c in classifications.values() if c == 'UNUSED')
    total = len(classifications)

    print(f"  Total files: {total}")
    print(f"  USED: {used} ({used/total*100:.1f}%)")
    print(f"  REACHABLE: {reachable} ({reachable/total*100:.1f}%)")
    print(f"  UNUSED: {unused} ({unused/total*100:.1f}%)")

if __name__ == "__main__":
    main()