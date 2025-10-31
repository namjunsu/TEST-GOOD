#!/usr/bin/env python3
"""
Cleanup Apply Script
7일 이상 격리된 파일을 최종 삭제
"""
import os
import csv
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import argparse


CSV_PATH = "scripts/cleanup_plan.csv"
QUARANTINE_DAYS = 7


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


def is_quarantine_expired(quarantine_date_str):
    """
    Check if quarantine period has expired

    Args:
        quarantine_date_str: Date string in YYYY-MM-DD format

    Returns:
        tuple: (expired: bool, days_remaining: int)
    """
    try:
        quarantine_date = datetime.strptime(quarantine_date_str, '%Y-%m-%d')
        expiry_date = quarantine_date + timedelta(days=QUARANTINE_DAYS)
        today = datetime.now()

        expired = today >= expiry_date
        days_remaining = (expiry_date - today).days

        return expired, days_remaining
    except ValueError:
        return False, 999


def delete_graveyard_file(record, dry_run=False):
    """
    Delete a file from graveyard

    Args:
        record: CSV record dict
        dry_run: If True, only simulate

    Returns:
        bool: True if deleted, False otherwise
    """
    graveyard_path = record['restore_method'].split()[1]  # Extract from 'mv <graveyard> <original>'

    if not os.path.exists(graveyard_path):
        print(f"⚠️  Graveyard file not found (already deleted?): {graveyard_path}")
        return False

    # Delete file
    if dry_run:
        print(f"🔍 [DRY RUN] Would delete: {graveyard_path}")
    else:
        if os.path.isdir(graveyard_path):
            shutil.rmtree(graveyard_path)
        else:
            os.remove(graveyard_path)
        print(f"🗑️  Deleted: {graveyard_path}")

    return True


def main():
    parser = argparse.ArgumentParser(description='Delete files after quarantine period')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without deleting')
    parser.add_argument('--force', action='store_true', help='Force delete all quarantined files (skip 7-day check)')

    args = parser.parse_args()

    print("=" * 80)
    print("🗑️  CLEANUP APPLY - Final Deletion")
    print("=" * 80)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be deleted")
        print()

    if args.force:
        print("⚠️  FORCE MODE - Skipping 7-day quarantine check")
        print()

    # Read plan
    rows = read_cleanup_plan()
    if not rows:
        return

    # Filter to quarantined files only
    quarantined = [r for r in rows if r['status'] == 'quarantined']

    if not quarantined:
        print("ℹ️  No quarantined files to delete")
        return

    print(f"Found {len(quarantined)} quarantined files")
    print()

    # Determine which files are ready for deletion
    ready_for_deletion = []
    not_ready = []

    for record in quarantined:
        expired, days_remaining = is_quarantine_expired(record['quarantine_date'])

        if args.force or expired:
            ready_for_deletion.append(record)
        else:
            not_ready.append((record, days_remaining))

    if not ready_for_deletion:
        print("ℹ️  No files ready for deletion (quarantine period not expired)")
        print()
        print("Files still in quarantine:")
        for record, days_remaining in not_ready:
            print(f"  - {record['path']} ({days_remaining} days remaining)")
        return

    print(f"Ready for deletion: {len(ready_for_deletion)} files")
    print()

    # Show files to be deleted
    print("Files to be deleted:")
    for record in ready_for_deletion:
        expired, _ = is_quarantine_expired(record['quarantine_date'])
        status = "EXPIRED" if expired else "FORCED"
        print(f"  [{status}] {record['path']} (quarantined: {record['quarantine_date']})")
    print()

    # Confirm unless dry-run
    if not args.dry_run and not args.force:
        response = input(f"⚠️  Delete {len(ready_for_deletion)} files permanently? [y/N]: ")
        if response.lower() != 'y':
            print("❌ Deletion cancelled")
            return

    # Delete files
    deleted_count = 0
    for record in ready_for_deletion:
        if delete_graveyard_file(record, dry_run=args.dry_run):
            if not args.dry_run:
                record['status'] = 'deleted'
            deleted_count += 1

    # Update CSV
    if deleted_count > 0 and not args.dry_run:
        write_cleanup_plan(rows)
        print()
        print(f"✅ Updated cleanup plan: {deleted_count} files deleted")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Files deleted: {deleted_count}/{len(ready_for_deletion)}")
    print(f"Files still in quarantine: {len(not_ready)}")


if __name__ == "__main__":
    main()
