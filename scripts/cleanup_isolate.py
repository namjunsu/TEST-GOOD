#!/usr/bin/env python3
"""
Cleanup Isolation Script
격리 → 보류 단계: 파일을 _graveyard로 이동하고 cleanup_plan.csv에 기록
"""
import os
import csv
import shutil
from pathlib import Path
from datetime import datetime
import argparse


GRAVEYARD_BASE = "experiments/namjunsu/20251031/_graveyard"
CSV_PATH = "scripts/cleanup_plan.csv"


def read_cleanup_plan():
    """Read existing cleanup plan"""
    if not os.path.exists(CSV_PATH):
        return []

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Skip comment lines
        rows = [row for row in reader if not row.get('path', '').startswith('#')]
    return rows


def write_cleanup_plan(rows):
    """Write cleanup plan to CSV"""
    fieldnames = ['path', 'reason', 'restore_method', 'quarantine_date', 'status']

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        f.write("path,reason,restore_method,quarantine_date,status\n")
        f.write("# Cleanup Plan - Safe File Quarantine Tracker\n")
        f.write("# Status values: pending, quarantined, deleted, restored\n")
        f.write("# Quarantine period: 7 days from quarantine_date\n")
        f.write("# Use 'make cleanup-isolate' to quarantine, 'make cleanup-apply' to delete after 7 days\n")

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def isolate_file(filepath, reason, dry_run=False):
    """
    Isolate a file to graveyard

    Args:
        filepath: Relative path from repo root
        reason: Reason for isolation
        dry_run: If True, only simulate

    Returns:
        dict: Isolation record
    """
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return None

    # Calculate graveyard path (preserve directory structure)
    rel_path = filepath.lstrip('./')
    graveyard_path = os.path.join(GRAVEYARD_BASE, rel_path)
    graveyard_dir = os.path.dirname(graveyard_path)

    # Create graveyard directory
    if not dry_run:
        os.makedirs(graveyard_dir, exist_ok=True)

    # Move file
    if dry_run:
        print(f"🔍 [DRY RUN] Would move: {filepath} → {graveyard_path}")
    else:
        shutil.move(filepath, graveyard_path)
        print(f"✅ Quarantined: {filepath} → {graveyard_path}")

    # Create record
    record = {
        'path': filepath,
        'reason': reason,
        'restore_method': f'mv {graveyard_path} {filepath}',
        'quarantine_date': datetime.now().strftime('%Y-%m-%d'),
        'status': 'quarantined' if not dry_run else 'pending'
    }

    return record


def main():
    parser = argparse.ArgumentParser(description='Isolate files to graveyard')
    parser.add_argument('files', nargs='*', help='Files to isolate')
    parser.add_argument('--reason', default='Manual isolation', help='Reason for isolation')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without moving files')
    parser.add_argument('--from-usage-audit', action='store_true', help='Use USAGE_AUDIT.md as source')

    args = parser.parse_args()

    print("=" * 80)
    print("🗑️  CLEANUP ISOLATION - Quarantine Files")
    print("=" * 80)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be moved")
        print()

    # Read existing plan
    existing_rows = read_cleanup_plan()
    existing_paths = {row['path'] for row in existing_rows}

    # Determine files to isolate
    files_to_isolate = []

    if args.from_usage_audit:
        # Parse USAGE_AUDIT.md for unused files
        print("📊 Reading USAGE_AUDIT.md for unused files...")
        if not os.path.exists('reports/USAGE_AUDIT.md'):
            print("❌ reports/USAGE_AUDIT.md not found")
            return

        with open('reports/USAGE_AUDIT.md', 'r') as f:
            content = f.read()

        # Extract file paths from markdown table
        import re
        pattern = r'\| `([^`]+)` \| UNUSED \|'
        matches = re.findall(pattern, content)

        # Filter out false positives (known-used files)
        false_positives = [
            './app/alerts.py',
            './app/rag/query_router.py',
            './app/rag/query_parser.py',
            './app/rag/pipeline.py',
            './app/rag/summary_templates.py',
            './app/rag/utils/context_hydrator.py',
            './app/rag/parse/doctype.py',
            './app/rag/parse/parse_meta.py',
            './app/rag/parse/parse_tables.py',
            './app/rag/preprocess/clean_text.py',
            './app/rag/render/list_postprocess.py',
            './app/rag/render/summary_templates.py',
            './app/rag/retrievers/exact_match.py',
            './app/rag/retrievers/hybrid.py',
            './app/rag/utils/json_utils.py',
        ]

        # Only include files from archive/, experiments/, and root-level test files
        for match in matches:
            if (match.startswith('./archive/') or
                match.startswith('./experiments/') or
                (match.startswith('./test_') and match.count('/') == 1) or
                match.startswith('./components/') or
                match.startswith('./modules/search_module') or
                match.startswith('./rag_system/') or
                match.startswith('./utils/') or
                match.startswith('./tests/')):

                if match not in false_positives:
                    files_to_isolate.append((match, 'Unused - from USAGE_AUDIT.md'))

        print(f"Found {len(files_to_isolate)} candidates for isolation")
        print()
    else:
        # Use command-line files
        for fpath in args.files:
            files_to_isolate.append((fpath, args.reason))

    if not files_to_isolate:
        print("ℹ️  No files to isolate")
        return

    # Isolate files
    new_records = []
    for filepath, reason in files_to_isolate:
        # Skip if already in plan
        if filepath in existing_paths:
            print(f"⏭️  Skipping {filepath} (already in plan)")
            continue

        record = isolate_file(filepath, reason, dry_run=args.dry_run)
        if record:
            new_records.append(record)

    # Update CSV
    if new_records and not args.dry_run:
        all_rows = existing_rows + new_records
        write_cleanup_plan(all_rows)
        print()
        print(f"✅ Updated cleanup plan: {len(new_records)} files quarantined")
        print(f"📄 CSV: {CSV_PATH}")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total files processed: {len(files_to_isolate)}")
    print(f"Newly quarantined: {len(new_records)}")
    print(f"Skipped (already in plan): {len(files_to_isolate) - len(new_records)}")
    print()

    if not args.dry_run and new_records:
        print("⏰ Files will be held in graveyard for 7 days")
        print("💡 To restore: make cleanup-restore")
        print("💡 To delete after 7 days: make cleanup-apply")


if __name__ == "__main__":
    main()
