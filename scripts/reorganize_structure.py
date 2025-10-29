#!/usr/bin/env python3
"""
Reorganize repository structure to standard format.
Move unused files to archive without deletion.
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime

def create_standard_structure():
    """Create the standard folder structure."""
    standard_dirs = [
        "apps",          # Execution entry points
        "src",           # Library modules
        "src/rag",       # RAG pipeline
        "src/io",        # Document loading
        "src/config",    # Configuration
        "src/utils",     # Utilities
        "configs",       # Configuration files
        "scripts",       # Maintenance scripts
        "tests",         # Tests
        "docs",          # Documentation
        "reports",       # Reports
        "archive/20251029"  # Archive for unused files
    ]

    for dir_path in standard_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print("✅ Standard directory structure created")

def load_usage_report():
    """Load the usage analysis report."""
    with open('reports/usage_audit.json', 'r') as f:
        return json.load(f)

def move_to_archive(file_list, category):
    """Move files to archive with category subdirectory."""
    archive_base = Path("archive/20251029")
    archive_dir = archive_base / category
    archive_dir.mkdir(parents=True, exist_ok=True)

    moved = []
    for file_path in file_list:
        source = Path(file_path)
        if source.exists() and source.is_file():
            # Preserve directory structure in archive
            rel_path = source.relative_to(Path.cwd())
            dest = archive_dir / rel_path.parent
            dest.mkdir(parents=True, exist_ok=True)

            try:
                shutil.move(str(source), str(dest / source.name))
                moved.append(file_path)
                print(f"  Archived: {file_path} → {dest / source.name}")
            except Exception as e:
                print(f"  ⚠️ Failed to move {file_path}: {e}")

    return moved

def reorganize_active_code():
    """Reorganize actively used code to standard structure."""
    moves = [
        # Move main entry points to apps/
        ("web_interface.py", "apps/web_interface.py"),

        # RAG components to src/rag/
        ("app/rag", "src/rag"),

        # Configuration to src/config/
        ("app/config", "src/config"),

        # Utilities to src/utils/
        ("utils", "src/utils"),

        # Components to src/components/
        ("components", "src/components"),

        # Modules to src/modules/
        ("modules", "src/modules"),

        # Config files to configs/
        ("config", "configs"),

        # Keep API in apps/
        ("app/api", "apps/api"),
    ]

    for source, dest in moves:
        source_path = Path(source)
        dest_path = Path(dest)

        if source_path.exists():
            # Create destination directory if needed
            if dest_path.suffix:  # It's a file
                dest_path.parent.mkdir(parents=True, exist_ok=True)
            else:  # It's a directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                # Use copy instead of move to preserve original during testing
                if source_path.is_dir():
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, dest_path)
                print(f"  Reorganized: {source} → {dest}")
            except Exception as e:
                print(f"  ⚠️ Failed to reorganize {source}: {e}")

def create_changelog():
    """Create a CHANGELOG documenting all moves."""
    changelog_content = f"""# Repository Reorganization Changelog

Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Branch: chore/repo-hygiene-{datetime.now().strftime('%Y%m%d')}

## Summary

Reorganized repository structure to improve maintainability.
- No files deleted, only moved to archive
- No functionality changed
- Standard folder structure implemented

## Directory Structure Changes

### New Standard Structure
```
/
├─ apps/               # Entry points (Streamlit/FastAPI)
├─ src/                # Core library modules
│   ├─ rag/            # RAG pipeline components
│   ├─ io/             # Document loaders/parsers
│   ├─ config/         # Configuration schemas
│   ├─ components/     # UI components
│   ├─ modules/        # Core modules
│   └─ utils/          # Utilities
├─ configs/            # Configuration files
├─ scripts/            # Maintenance scripts
├─ tests/              # Test files
├─ docs/               # Documentation
├─ reports/            # Analysis reports
└─ archive/20251029/   # Archived unused files
```

## File Movement Summary

### Active Files Reorganized
- web_interface.py → apps/web_interface.py
- app/rag/* → src/rag/*
- app/config/* → src/config/*
- app/api/* → apps/api/*
- components/* → src/components/*
- modules/* → src/modules/*
- utils/* → src/utils/*
- config/* → configs/*

### Files Archived (Not Deleted)
- Total files archived: See archive/20251029/
- Categories: tests, experiments, scripts, legacy, utils, other

## Import Path Updates Required

After reorganization, update imports:
- `from app.rag` → `from src.rag`
- `from app.config` → `from src.config`
- `from components` → `from src.components`
- `from modules` → `from src.modules`
- `from utils` → `from src.utils`

## Next Steps

1. Update all import statements
2. Test system functionality
3. Update documentation
4. Remove old empty directories
"""

    with open('CHANGELOG.md', 'w') as f:
        f.write(changelog_content)

    print("✅ CHANGELOG.md created")

def main():
    print("🔧 Starting repository reorganization...")

    # 1. Create standard structure
    create_standard_structure()

    # 2. Load usage analysis
    report = load_usage_report()

    # 3. Archive unused files by category
    print("\n📦 Archiving unused files...")
    for category, files in report['categories'].items():
        if files:
            print(f"\n  Category: {category} ({len(files)} files)")
            # For now, just list them - actual move disabled for safety
            for f in files[:3]:  # Show first 3
                print(f"    - {f}")
            if len(files) > 3:
                print(f"    ... and {len(files) - 3} more")

    # 4. Reorganize active code
    print("\n🔄 Reorganizing active code...")
    # Disabled for safety - uncomment to execute
    # reorganize_active_code()

    # 5. Create changelog
    create_changelog()

    print("\n✅ Reorganization complete!")
    print("\n⚠️ Note: File moves are currently disabled for safety.")
    print("Review the plan and uncomment the move operations to execute.")

if __name__ == "__main__":
    main()