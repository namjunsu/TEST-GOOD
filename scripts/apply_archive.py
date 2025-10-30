#!/usr/bin/env python3
"""
Apply archive move for unused files identified by X-Ray analysis.
IMPORTANT: Does NOT delete files, only moves to archive.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
import json

def create_archive_dir():
    """Create archive directory with date stamp."""
    archive_dir = Path(f"archive/{datetime.now().strftime('%Y%m%d')}")
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir

def read_candidates(candidates_file='reports/xray/archive_candidates.txt'):
    """Read list of files to archive."""
    if not Path(candidates_file).exists():
        print(f"❌ Candidates file not found: {candidates_file}")
        return []

    with open(candidates_file, 'r') as f:
        candidates = [line.strip() for line in f if line.strip()]

    return candidates

def safe_move(source, archive_dir):
    """Safely move file to archive, preserving directory structure."""
    source_path = Path(source)

    if not source_path.exists():
        print(f"  ⚠️  File not found: {source}")
        return False

    # Skip if it's an __init__.py (might be needed for imports)
    if source_path.name == '__init__.py':
        print(f"  ⏭️  Skipping __init__.py: {source}")
        return False

    # Create target path preserving structure
    target_path = archive_dir / source_path

    # Create parent directories
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Move file
    try:
        shutil.move(str(source_path), str(target_path))
        print(f"  ✅ Moved: {source} → {target_path}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to move {source}: {e}")
        return False

def generate_archive_log(archive_dir, moved_files):
    """Generate log file in archive directory."""
    log_file = archive_dir / 'ARCHIVE_LOG.md'

    with open(log_file, 'w') as f:
        f.write(f"# Archive Log\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total files archived: {len(moved_files)}\n\n")

        f.write("## Archived Files\n\n")
        for file in sorted(moved_files):
            f.write(f"- {file}\n")

        f.write("\n## Restore Instructions\n\n")
        f.write("To restore a file:\n")
        f.write("```bash\n")
        f.write("# Single file\n")
        f.write("mv archive/YYYYMMDD/path/to/file.py path/to/file.py\n\n")
        f.write("# All files\n")
        f.write("cp -r archive/YYYYMMDD/* .\n")
        f.write("```\n")

    print(f"\n📝 Archive log created: {log_file}")

def main():
    print("="*60)
    print("ARCHIVE UNUSED FILES")
    print("="*60)

    # Read candidates
    candidates = read_candidates()
    print(f"\nFound {len(candidates)} files to archive\n")

    if not candidates:
        print("No files to archive. Exiting.")
        return

    # Filter out critical files we should never archive
    critical_files = {'config.py', 'web_interface.py', 'start_ai_chat.sh'}
    safe_candidates = [c for c in candidates if Path(c).name not in critical_files]

    if len(safe_candidates) < len(candidates):
        print(f"⚠️  Filtered out {len(candidates) - len(safe_candidates)} critical files\n")

    # Confirm
    print(f"Will archive {len(safe_candidates)} files:")
    for candidate in safe_candidates[:10]:
        print(f"  - {candidate}")
    if len(safe_candidates) > 10:
        print(f"  ... and {len(safe_candidates)-10} more")

    response = input("\nProceed with archiving? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return

    # Create archive directory
    archive_dir = create_archive_dir()
    print(f"\n📁 Archive directory: {archive_dir}\n")

    # Move files
    moved_files = []
    for candidate in safe_candidates:
        if safe_move(candidate, archive_dir):
            moved_files.append(candidate)

    # Generate log
    generate_archive_log(archive_dir, moved_files)

    # Summary
    print("\n" + "="*60)
    print(f"ARCHIVE COMPLETE")
    print("="*60)
    print(f"✅ Moved {len(moved_files)} files to {archive_dir}")
    print(f"❌ Skipped {len(safe_candidates) - len(moved_files)} files")
    print()

    # Test imports still work
    print("Testing imports...")
    try:
        import app.api.main
        import modules.metadata_db
        print("✅ Critical imports still working")
    except ImportError as e:
        print(f"⚠️  Import error: {e}")
        print("You may need to restore some files!")

    return moved_files

if __name__ == "__main__":
    moved = main()
    if moved:
        print("\nNext steps:")
        print("1. Run tests: pytest -q")
        print("2. Check app still works: ./start_ai_chat.sh")
        print("3. Commit changes: git add -A && git commit -m 'Archive unused modules'")