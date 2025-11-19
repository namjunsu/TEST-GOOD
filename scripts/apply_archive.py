#!/usr/bin/env python3
"""
Apply archive move for unused files identified by X-Ray analysis.
IMPORTANT: Does NOT delete files, only moves to archive.
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path.cwd().resolve()


def create_archive_dir() -> Path:
    """Create archive directory with date stamp under project root."""
    archive_dir = PROJECT_ROOT / "archive" / datetime.now().strftime("%Y%m%d")
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def read_candidates(candidates_file: str = "reports/xray/archive_candidates.txt") -> list[str]:
    """Read list of files to archive (raw strings)."""
    candidates_path = PROJECT_ROOT / candidates_file
    if not candidates_path.exists():
        print(f"❌ Candidates file not found: {candidates_path}")
        return []

    with open(candidates_path, "r", encoding="utf-8") as f:
        candidates = [line.strip() for line in f if line.strip()]

    return candidates


def normalize_path(path_str: str) -> Path | None:
    """
    Normalize candidate path to project-root-relative Path.

    - Accepts absolute or relative paths.
    - Skips anything outside PROJECT_ROOT.
    """
    p = Path(path_str.strip())
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()

    try:
        rel = p.relative_to(PROJECT_ROOT)
    except ValueError:
        print(f"  ⚠️  Outside project root, skipping: {p}")
        return None

    return rel


CRITICAL_PATHS = {
    "config.py",
    "web_interface.py",
    "start_ai_chat.sh",
    # 필요하면 여기에 경로 단위로 추가:
    # "app/api/main.py",
}


def is_critical(rel_path: Path) -> bool:
    """Return True if this file must never be archived."""
    name = rel_path.name
    if name in CRITICAL_PATHS:
        return True
    # 경로 기준으로 더 엄격하게 체크하려면 여기서 처리
    return False


def safe_move(rel_path: Path, archive_dir: Path) -> bool:
    """Safely move file to archive, preserving directory structure."""
    source_path = PROJECT_ROOT / rel_path

    if not source_path.exists():
        print(f"  ⚠️  File not found: {rel_path}")
        return False

    # Skip if it's an __init__.py (might be needed for imports)
    if source_path.name == "__init__.py":
        print(f"  ⏭️  Skipping __init__.py: {rel_path}")
        return False

    target_path = archive_dir / rel_path

    # Create parent directories
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(source_path), str(target_path))
        print(f"  ✅ Moved: {rel_path} → {target_path}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to move {rel_path}: {e}")
        return False


def generate_archive_log(archive_dir: Path, moved_files: list[Path]) -> None:
    """Generate log file in archive directory."""
    log_file = archive_dir / "ARCHIVE_LOG.md"

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("# Archive Log\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Project root: {PROJECT_ROOT}\n")
        f.write(f"Archive dir: {archive_dir}\n")
        f.write(f"Total files archived: {len(moved_files)}\n\n")

        f.write("## Archived Files (project-root-relative)\n\n")
        for file in sorted(moved_files, key=lambda p: str(p)):
            f.write(f"- {file.as_posix()}\n")

        f.write("\n## Restore Instructions\n\n")
        f.write("To restore a file (example):\n")
        f.write("```bash\n")
        f.write("# Single file (recommended)\n")
        f.write("cp archive/YYYYMMDD/path/to/file.py path/to/file.py\n\n")
        f.write("# Restore all (use with caution, may overwrite newer files)\n")
        f.write("rsync -av archive/YYYYMMDD/ .\n")
        f.write("```\n")

    print(f"\n📝 Archive log created: {log_file}")


def main(candidates_file: str | None = None):
    print("=" * 60)
    print("ARCHIVE UNUSED FILES")
    print("=" * 60)
    print(f"Project root: {PROJECT_ROOT}\n")

    # Default candidates file
    if candidates_file is None:
        candidates_file = "reports/xray/archive_candidates.txt"

    print(f"Using candidates file: {candidates_file}\n")

    # Read candidates
    raw_candidates = read_candidates(candidates_file)
    print(f"\nFound {len(raw_candidates)} raw candidates\n")

    if not raw_candidates:
        print("No files to archive. Exiting.")
        return

    # Normalize & filter outside project
    normalized: list[Path] = []
    for c in raw_candidates:
        rel = normalize_path(c)
        if rel is not None:
            normalized.append(rel)

    print(f"Valid candidates inside project: {len(normalized)}")

    # Filter out critical files
    safe_candidates = [p for p in normalized if not is_critical(p)]
    filtered_count = len(normalized) - len(safe_candidates)
    if filtered_count > 0:
        print(f"⚠️  Filtered out {filtered_count} critical files\n")

    if not safe_candidates:
        print("No safe candidates to archive. Exiting.")
        return

    # Preview
    print(f"Will archive {len(safe_candidates)} files:")
    for candidate in safe_candidates[:10]:
        print(f"  - {candidate.as_posix()}")
    if len(safe_candidates) > 10:
        print(f"  ... and {len(safe_candidates) - 10} more")

    response = input("\nProceed with archiving? (yes/no): ").strip().lower()
    if response != "yes":
        print("Aborted.")
        return

    # Create archive directory
    archive_dir = create_archive_dir()
    print(f"\n📁 Archive directory: {archive_dir}\n")

    # Move files
    moved_files: list[Path] = []
    for candidate in safe_candidates:
        if safe_move(candidate, archive_dir):
            moved_files.append(candidate)

    # Generate log
    generate_archive_log(archive_dir, moved_files)

    # Summary
    print("\n" + "=" * 60)
    print("ARCHIVE COMPLETE")
    print("=" * 60)
    print(f"✅ Moved {len(moved_files)} files to {archive_dir}")
    print(f"❌ Skipped {len(safe_candidates) - len(moved_files)} files\n")

    # Test imports still work (skip if no files were moved)
    if moved_files:
        print("Testing imports...")
        result = subprocess.run(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                "-c",
                "import app.api.main; import app.data.metadata_db; print('✅ Critical imports working')",
            ],
            env={"PYTHONPATH": str(PROJECT_ROOT)},
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout.strip().split("\n")[-1])  # Last line only
        else:
            print(f"⚠️  Import error: {result.stderr}")
            print("You may need to restore some files!")

    return moved_files


if __name__ == "__main__":
    # Support CLI argument for custom candidates file
    candidates_file = sys.argv[1] if len(sys.argv) > 1 else None
    moved = main(candidates_file)
    if moved:
        print("\nNext steps:")
        print("1. Run tests: pytest -q")
        print("2. Check app still works: ./start_ai_chat.sh")
        print("3. Commit changes: git add -A && git commit -m 'Archive unused modules'")
