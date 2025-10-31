#!/usr/bin/env python3
"""
Cleanup Restore Script
격리된 파일을 원위치로 복원
"""
import os
import csv
import shutil
from pathlib import Path
import argparse


CSV_PATH = "scripts/cleanup_plan.csv"


def read_cleanup_plan():
    """Read cleanup plan"""
    if not os.path.exists(CSV_PATH):
        print(f"❌ {CSV_PATH} not found")
        return []

    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
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


def restore_file(record, dry_run=False):
    """
    Restore a file from graveyard

    Args:
        record: CSV record dict
        dry_run: If True, only simulate

    Returns:
        bool: True if restored, False otherwise
    """
    filepath = record['path']
    graveyard_path = record['restore_method'].split()[1]  # Extract from 'mv <graveyard> <original>'

    if not os.path.exists(graveyard_path):
        print(f"⚠️  Graveyard file not found: {graveyard_path}")
        return False

    if os.path.exists(filepath):
        print(f"⚠️  Target already exists: {filepath} (skipping)")
        return False

    # Ensure parent directory exists
    parent_dir = os.path.dirname(filepath)
    if parent_dir and not dry_run:
        os.makedirs(parent_dir, exist_ok=True)

    # Restore file
    if dry_run:
        print(f"🔍 [DRY RUN] Would restore: {graveyard_path} → {filepath}")
    else:
        shutil.move(graveyard_path, filepath)
        print(f"✅ Restored: {graveyard_path} → {filepath}")

    return True


def main():
    parser = argparse.ArgumentParser(description='Restore files from graveyard')
    parser.add_argument('files', nargs='*', help='Specific files to restore (or all if empty)')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without restoring')
    parser.add_argument('--all', action='store_true', help='Restore all quarantined files')

    args = parser.parse_args()

    print("=" * 80)
    print("♻️  CLEANUP RESTORE - Restore from Graveyard")
    print("=" * 80)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be restored")
        print()

    # Read plan
    rows = read_cleanup_plan()
    if not rows:
        return

    # Filter to quarantined files only
    quarantined = [r for r in rows if r['status'] == 'quarantined']

    if not quarantined:
        print("ℹ️  No quarantined files to restore")
        return

    print(f"Found {len(quarantined)} quarantined files")
    print()

    # Determine which files to restore
    if args.all:
        to_restore = quarantined
    elif args.files:
        # Filter by specified files
        file_set = set(args.files)
        to_restore = [r for r in quarantined if r['path'] in file_set]
    else:
        print("ℹ️  Specify files to restore or use --all")
        print()
        print("Quarantined files:")
        for r in quarantined:
            print(f"  - {r['path']} (quarantined: {r['quarantine_date']})")
        return

    if not to_restore:
        print("⚠️  No matching files found")
        return

    # Restore files
    restored_count = 0
    for record in to_restore:
        if restore_file(record, dry_run=args.dry_run):
            if not args.dry_run:
                record['status'] = 'restored'
            restored_count += 1

    # Update CSV
    if restored_count > 0 and not args.dry_run:
        write_cleanup_plan(rows)
        print()
        print(f"✅ Updated cleanup plan: {restored_count} files restored")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Files restored: {restored_count}/{len(to_restore)}")


if __name__ == "__main__":
    main()
