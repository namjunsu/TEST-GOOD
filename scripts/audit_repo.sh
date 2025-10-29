#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
echo "[1/5] Freeze"
python -V | tee reports/python_version.txt
pip freeze > reports/pip_freeze.txt || true

echo "[2/5] Pip dependency tree"
pip install -q pipdeptree vulture >/dev/null 2>&1 || true
pipdeptree --json > reports/pipdeptree.json 2>/dev/null || true

echo "[3/5] Dead code"
vulture . --min-confidence 80 --sort-by-size > reports/vulture.txt 2>/dev/null || true

echo "[4/5] Repo stats"
python - <<'PY'
import json, os
from pathlib import Path

# Count Python files and lines
stats = {"py_files": 0, "lines": 0, "folders": set(), "modules": set()}

for root, dirs, files in os.walk("."):
    # Skip hidden and cache directories
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

    for file in files:
        if file.endswith('.py'):
            stats["py_files"] += 1
            filepath = Path(root) / file
            stats["folders"].add(root)

            # Extract module name
            if root != '.':
                stats["modules"].add(root.replace('./', '').replace('/', '.').split('.')[0])

            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    stats["lines"] += sum(1 for _ in f)
            except:
                pass

# Convert sets to lists for JSON serialization
stats["folders"] = sorted(list(stats["folders"]))
stats["modules"] = sorted(list(stats["modules"]))

with open("reports/src_stats.json", "w") as f:
    json.dump(stats, f, indent=2)

print(f"Found {stats['py_files']} Python files with {stats['lines']} lines")
print(f"Across {len(stats['folders'])} folders and {len(stats['modules'])} top-level modules")
PY

echo "[5/5] Creating entrypoints report"
cat > reports/entrypoints.md <<'EOF'
# Execution Entrypoints Analysis

## Main Execution Scripts

### 1. Primary Script: `start_ai_chat.sh`
- **Status**: Active, executable (+x)
- **Purpose**: Main system launcher
- **Actions**:
  1. Activates Python virtual environment (.venv)
  2. Runs system checks (utils/system_checker.py)
  3. Starts FastAPI backend (port 7860): `uvicorn app.api.main:app`
  4. Starts Streamlit UI (port 8501): `streamlit run web_interface.py`
- **Environment Variables**:
  - AI_CHAT_PORT (default: 8501)
  - AI_CHAT_HOST (default: 0.0.0.0)
  - AI_CHAT_VENV (default: .venv)

### 2. Legacy Script: `run_rag.sh`
- **Status**: Deprecated (no execute permission)
- **References**: src/web_interface.py (non-existent path)
- **Action Required**: Move to archive

## Python Entry Points

### Primary
- `web_interface.py`: Streamlit UI main application
- `app/api/main.py`: FastAPI REST API server

### Utility Scripts
- `health_check.py`: System health verification
- `diagnose_qa_flow.py`: QA flow diagnostic tool
- `rebuild_metadata.py`: Database rebuilding
- `rebuild_rag_indexes.py`: Index recreation
- `fix_metadata_db.py`: Database repair
- `check_db_content.py`: Database content verification
- `everything_like_search.py`: Search testing
- `verify_golden_queries.py`: Query validation

### Test Scripts
- `test_e2e_validation.py`: End-to-end tests
- `test_final_validation.py`: Final validation tests
EOF

echo "✅ Audit complete -> reports/"
ls -la reports/