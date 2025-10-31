#!/bin/bash
# Simple ops checklist without external dependencies
set -euo pipefail

LOG_FILE="reports/ops_check.json"
mkdir -p reports

echo "📋 Running Operations Checklist (Simple)..."
echo ""

# Disk space check
echo "1. Disk Space:"
df -h . | tail -1
echo ""

# Memory check
echo "2. Memory:"
free -h | grep Mem
echo ""

# Port check
echo "3. Port Status:"
echo -n "   Port 8501: "
lsof -i :8501 >/dev/null 2>&1 && echo "In use" || echo "Free"
echo -n "   Port 7860: "
lsof -i :7860 >/dev/null 2>&1 && echo "In use" || echo "Free"
echo ""

# Database check
echo "4. Database Files:"
ls -lh *.db 2>/dev/null || echo "   No database files found"
echo ""

# Critical files check
echo "5. Critical Files:"
for file in web_interface.py app/api/main.py app/rag/pipeline.py config.py .env requirements.txt; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ $file (missing)"
    fi
done
echo ""

# Python version
echo "6. Python Version:"
python3 --version
echo ""

# Document count
echo "7. Document Count:"
python3 -c "
from modules.metadata_db import MetadataDB
db = MetadataDB()
count = db.count_documents()
print(f'   Documents: {count} (expected: 483)')
print(f'   Status: {\"✅ OK\" if count == 483 else \"⚠️ Mismatch\"}')"
echo ""

# Generate JSON report
python3 -c "
import json
import subprocess
import os

report = {
    'timestamp': subprocess.check_output(['date']).decode().strip(),
    'checks': {
        'disk_space': 'Check df -h output above',
        'memory': 'Check free -h output above',
        'ports': {
            '8501': 'Check lsof output above',
            '7860': 'Check lsof output above'
        },
        'databases': {
            'metadata.db': os.path.exists('metadata.db'),
            'everything_index.db': os.path.exists('everything_index.db')
        },
        'critical_files': {
            'web_interface.py': os.path.exists('web_interface.py'),
            'app/api/main.py': os.path.exists('app/api/main.py'),
            'app/rag/pipeline.py': os.path.exists('app/rag/pipeline.py'),
            'config.py': os.path.exists('config.py'),
            '.env': os.path.exists('.env'),
            'requirements.txt': os.path.exists('requirements.txt')
        }
    }
}

with open('$LOG_FILE', 'w') as f:
    json.dump(report, f, indent=2)
"

echo "📊 Summary:"
echo "-----------"
echo "✅ Ops checklist complete"
echo "📄 Report saved to: $LOG_FILE"