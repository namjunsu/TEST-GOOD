#!/usr/bin/env python3
"""
Build code dependency map and module atlas for the codebase.
Generates import graphs and module metadata.
"""

import ast
import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import networkx as nx
from collections import defaultdict

class PythonModuleAnalyzer:
    """Analyzes Python modules to extract dependencies and metadata."""

    def __init__(self, roots: List[str]):
        self.roots = [Path(r).resolve() for r in roots]
        self.modules = {}  # path -> module_info
        self.import_graph = nx.DiGraph()
        self.base_path = Path.cwd()

    def analyze(self):
        """Analyze all Python files in the specified roots."""
        for root in self.roots:
            if root.exists():
                self._scan_directory(root)

        # Build import relationships
        self._build_import_graph()

        return self.modules, self.import_graph

    def _scan_directory(self, directory: Path):
        """Recursively scan a directory for Python files."""
        for py_file in directory.rglob("*.py"):
            # Skip virtual env, cache, and test files
            if any(skip in str(py_file) for skip in ['.venv', '__pycache__', 'archive']):
                continue

            self._analyze_file(py_file)

    def _analyze_file(self, filepath: Path):
        """Analyze a single Python file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, str(filepath))

            # Extract module information
            module_info = {
                'path': str(filepath.relative_to(self.base_path)),
                'absolute_path': str(filepath),
                'lines_of_code': len(content.splitlines()),
                'imports': [],
                'functions': [],
                'classes': [],
                'entry_point': False,
                'docstring': ast.get_docstring(tree)
            }

            # Visit all nodes
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_info['imports'].append(alias.name)

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_info['imports'].append(node.module)
                        # Also track specific imports
                        for alias in node.names:
                            if alias.name != '*':
                                module_info['imports'].append(f"{node.module}.{alias.name}")

                elif isinstance(node, ast.FunctionDef):
                    func_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'args': [arg.arg for arg in node.args.args],
                        'is_async': False
                    }
                    module_info['functions'].append(func_info)

                elif isinstance(node, ast.AsyncFunctionDef):
                    func_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'args': [arg.arg for arg in node.args.args],
                        'is_async': True
                    }
                    module_info['functions'].append(func_info)

                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'methods': [],
                        'bases': []
                    }

                    # Get base classes
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            class_info['bases'].append(base.id)
                        elif isinstance(base, ast.Attribute):
                            class_info['bases'].append(ast.unparse(base))

                    # Get methods
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            class_info['methods'].append(item.name)

                    module_info['classes'].append(class_info)

            # Check if it's an entry point
            if '__main__' in content:
                module_info['entry_point'] = True

            # Store module info
            module_key = self._path_to_module(filepath)
            self.modules[module_key] = module_info
            self.import_graph.add_node(module_key)

        except Exception as e:
            print(f"Error analyzing {filepath}: {e}", file=sys.stderr)

    def _path_to_module(self, filepath: Path) -> str:
        """Convert file path to module name."""
        # Remove .py extension and convert to module format
        relative = filepath.relative_to(self.base_path)
        module = str(relative).replace('.py', '').replace(os.sep, '.')
        return module

    def _build_import_graph(self):
        """Build the import dependency graph."""
        for module_name, info in self.modules.items():
            for imp in info['imports']:
                # Try to resolve import to a module in our codebase
                resolved = self._resolve_import(module_name, imp)
                if resolved and resolved in self.modules:
                    self.import_graph.add_edge(module_name, resolved)

    def _resolve_import(self, from_module: str, import_name: str) -> Optional[str]:
        """Resolve an import to a module in our codebase."""
        # Direct module match
        if import_name in self.modules:
            return import_name

        # Try relative imports
        if '.' in from_module:
            package = '.'.join(from_module.split('.')[:-1])
            potential = f"{package}.{import_name}"
            if potential in self.modules:
                return potential

        # Try app/src roots
        for prefix in ['app', 'apps', 'src', 'modules']:
            potential = f"{prefix}.{import_name}"
            if potential in self.modules:
                return potential

            # Also try without the first part of import
            if '.' in import_name:
                parts = import_name.split('.')
                potential = f"{prefix}.{parts[0]}"
                if potential in self.modules:
                    return potential

        return None

def generate_dot_graph(graph: nx.DiGraph, output_path: str):
    """Generate DOT format graph file."""
    with open(output_path, 'w') as f:
        f.write("digraph dependencies {\n")
        f.write('  rankdir="LR";\n')
        f.write('  node [shape=box, style=filled, fillcolor=lightblue];\n')

        # Highlight entry points
        entry_nodes = set()
        for node in graph.nodes():
            if node.startswith('app') or node.startswith('web_interface'):
                entry_nodes.add(node)
                f.write(f'  "{node}" [fillcolor=lightgreen, style="filled,bold"];\n')

        # Write edges
        for source, target in graph.edges():
            f.write(f'  "{source}" -> "{target}";\n')

        f.write("}\n")

def main():
    parser = argparse.ArgumentParser(description='Build code dependency map')
    parser.add_argument('--roots', nargs='+', default=['src', 'app', 'apps', 'modules'],
                       help='Root directories to analyze')
    parser.add_argument('--out-dir', default='docs/xray',
                       help='Output directory for results')
    parser.add_argument('--graph', default='reports/xray/IMPORT_GRAPH.dot',
                       help='Output path for dependency graph')

    args = parser.parse_args()

    # Create output directories
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    Path(args.graph).parent.mkdir(parents=True, exist_ok=True)

    # Analyze codebase
    print("Analyzing Python modules...")
    analyzer = PythonModuleAnalyzer(args.roots)
    modules, graph = analyzer.analyze()

    print(f"Found {len(modules)} modules with {graph.number_of_edges()} dependencies")

    # Generate dependency graph
    print(f"Generating dependency graph: {args.graph}")
    generate_dot_graph(graph, args.graph)

    # Save module metadata
    metadata_path = Path(args.out_dir) / 'modules_metadata.json'
    print(f"Saving module metadata: {metadata_path}")
    with open(metadata_path, 'w') as f:
        json.dump(modules, f, indent=2, default=str)

    # Generate statistics
    stats = {
        'total_modules': len(modules),
        'total_dependencies': graph.number_of_edges(),
        'entry_points': sum(1 for m in modules.values() if m['entry_point']),
        'total_functions': sum(len(m['functions']) for m in modules.values()),
        'total_classes': sum(len(m['classes']) for m in modules.values()),
        'total_lines': sum(m['lines_of_code'] for m in modules.values()),
        'isolated_modules': len([n for n in graph.nodes() if graph.degree(n) == 0])
    }

    stats_path = Path(args.out_dir) / 'analysis_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print("\nAnalysis Summary:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\nDone! Generated files:")
    print(f"  - {args.graph}")
    print(f"  - {metadata_path}")
    print(f"  - {stats_path}")

if __name__ == "__main__":
    main()