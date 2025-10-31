#!/usr/bin/env python3
"""
Corrected X-Ray analysis with proper file scanning.
"""

import os
import sys
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime

def load_coverage(coverage_xml):
    """Load coverage data from XML."""
    coverage_data = {}

    if not Path(coverage_xml).exists():
        return coverage_data

    try:
        tree = ET.parse(coverage_xml)
        root = tree.getroot()

        for package in root.findall('.//package'):
            for cls in package.findall('classes/class'):
                filename = cls.get('filename')
                if filename:
                    # Normalize path
                    lines_covered = 0
                    lines_total = 0
                    for line in cls.findall('lines/line'):
                        lines_total += 1
                        if line.get('hits', '0') != '0':
                            lines_covered += 1

                    coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 0
                    coverage_data[filename] = {
                        'covered_lines': lines_covered,
                        'total_lines': lines_total,
                        'coverage_percent': coverage_pct
                    }
    except Exception as e:
        print(f"Error loading coverage: {e}")

    return coverage_data

def find_python_files():
    """Find all relevant Python files."""
    files = []

    # Root level Python files
    for f in Path('.').glob('*.py'):
        if not str(f).startswith('.'):
            files.append(str(f))

    # Module directories
    for root_dir in ['app', 'apps', 'modules', 'src']:
        if Path(root_dir).exists():
            for py_file in Path(root_dir).rglob('*.py'):
                if '__pycache__' not in str(py_file) and 'archive' not in str(py_file):
                    files.append(str(py_file))

    return sorted(set(files))

def classify_files(files, coverage_data):
    """Classify files as USED, REACHABLE, or UNUSED."""
    classifications = {}

    # Entry points
    entry_points = {
        'web_interface.py',
        'app/api/main.py',
        'config.py',
    }

    # Known reachable from imports
    reachable = {
        'app/core/logging.py',
        'app/config/settings.py',
        'modules/metadata_db.py',
        'modules/metadata_extractor.py',
        'modules/search_module.py',
        'modules/search_module_hybrid.py',
    }

    for filepath in files:
        # Check if file has coverage
        has_coverage = False
        for cov_path in coverage_data:
            if filepath in cov_path or cov_path in filepath:
                if coverage_data[cov_path]['coverage_percent'] > 0:
                    has_coverage = True
                    break

        if has_coverage:
            classifications[filepath] = 'USED'
        elif any(ep in filepath for ep in entry_points):
            classifications[filepath] = 'REACHABLE'
        elif any(r in filepath for r in reachable):
            classifications[filepath] = 'REACHABLE'
        else:
            classifications[filepath] = 'UNUSED'

    return classifications

def generate_report(classifications, coverage_data):
    """Generate summary report."""
    used = sum(1 for c in classifications.values() if c == 'USED')
    reachable = sum(1 for c in classifications.values() if c == 'REACHABLE')
    unused = sum(1 for c in classifications.values() if c == 'UNUSED')
    total = len(classifications)

    print("\n" + "="*60)
    print("X-RAY ANALYSIS RESULTS")
    print("="*60)
    print(f"Total Python files: {total}")
    print(f"  USED (with coverage): {used} ({used/total*100:.1f}%)")
    print(f"  REACHABLE (entry/import): {reachable} ({reachable/total*100:.1f}%)")
    print(f"  UNUSED (no coverage/reach): {unused} ({unused/total*100:.1f}%)")
    print()

    # Show top USED files
    if used > 0:
        print("TOP USED FILES (with coverage):")
        used_files = [(f, c) for f, c in classifications.items() if c == 'USED']
        for filepath, _ in sorted(used_files)[:10]:
            cov_info = None
            for cov_path in coverage_data:
                if filepath in cov_path or cov_path in filepath:
                    cov_info = coverage_data[cov_path]
                    break
            if cov_info:
                print(f"  ✅ {filepath} ({cov_info['coverage_percent']:.1f}%)")
            else:
                print(f"  ✅ {filepath}")

    # Show UNUSED files (candidates for archiving)
    if unused > 0:
        print("\nUNUSED FILES (archive candidates):")
        unused_files = [f for f, c in classifications.items() if c == 'UNUSED']
        for filepath in sorted(unused_files)[:20]:
            print(f"  ❌ {filepath}")
        if len(unused_files) > 20:
            print(f"  ... and {len(unused_files)-20} more")

    return {
        'total': total,
        'used': used,
        'reachable': reachable,
        'unused': unused
    }

def save_csv(classifications, coverage_data, output_file):
    """Save classifications to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['File', 'Classification', 'Coverage%', 'Covered Lines', 'Total Lines'])

        for filepath in sorted(classifications.keys()):
            classification = classifications[filepath]
            cov_info = None

            for cov_path in coverage_data:
                if filepath in cov_path or cov_path in filepath:
                    cov_info = coverage_data[cov_path]
                    break

            if cov_info:
                writer.writerow([
                    filepath,
                    classification,
                    f"{cov_info['coverage_percent']:.1f}",
                    cov_info['covered_lines'],
                    cov_info['total_lines']
                ])
            else:
                writer.writerow([filepath, classification, '0.0', 0, 0])

    print(f"Saved CSV: {output_file}")

def main():
    # Load coverage data
    print("Loading coverage data...")
    coverage_data = load_coverage('reports/xray/coverage.xml')
    print(f"Found coverage for {len(coverage_data)} files")

    # Find Python files
    print("Scanning Python files...")
    files = find_python_files()
    print(f"Found {len(files)} Python files")

    # Classify files
    print("Classifying files...")
    classifications = classify_files(files, coverage_data)

    # Generate report
    stats = generate_report(classifications, coverage_data)

    # Save CSV
    save_csv(classifications, coverage_data, 'reports/xray/coverage_map_corrected.csv')

    # Save reachable files
    reachable = [f for f, c in classifications.items() if c in ['USED', 'REACHABLE']]
    with open('reports/xray/reachable_modules_corrected.txt', 'w') as f:
        f.write('\n'.join(sorted(reachable)))
    print(f"Saved reachable list: reports/xray/reachable_modules_corrected.txt")

    # Save unused files (archive candidates)
    unused = [f for f, c in classifications.items() if c == 'UNUSED']
    with open('reports/xray/archive_candidates.txt', 'w') as f:
        f.write('\n'.join(sorted(unused)))
    print(f"Saved archive candidates: reports/xray/archive_candidates.txt")

    return stats

if __name__ == "__main__":
    main()