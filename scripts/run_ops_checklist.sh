#!/bin/bash
# Run operations checklist
set -euo pipefail

LOG_FILE="reports/ops_check.json"
mkdir -p reports

echo "📋 Running Operations Checklist..."

# Collect system metrics
python3 -c "
import json
import os
import shutil
import psutil
import sqlite3
from pathlib import Path
import subprocess

report = {
    'timestamp': subprocess.check_output(['date']).decode().strip(),
    'system': {},
    'disk': {},
    'memory': {},
    'database': {},
    'ports': {},
    'files': {},
    'git': {}
}

# Disk space
disk_usage = shutil.disk_usage('.')
report['disk'] = {
    'total_gb': round(disk_usage.total / (1024**3), 2),
    'used_gb': round(disk_usage.used / (1024**3), 2),
    'free_gb': round(disk_usage.free / (1024**3), 2),
    'percent': round(disk_usage.used / disk_usage.total * 100, 1)
}

# Memory
mem = psutil.virtual_memory()
report['memory'] = {
    'total_gb': round(mem.total / (1024**3), 2),
    'available_gb': round(mem.available / (1024**3), 2),
    'percent': mem.percent
}

# Database sizes
for db_file in ['metadata.db', 'everything_index.db']:
    if os.path.exists(db_file):
        size_mb = os.path.getsize(db_file) / (1024**2)
        report['database'][db_file] = {
            'size_mb': round(size_mb, 2),
            'exists': True
        }

        # Count records
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.execute('SELECT COUNT(*) FROM documents')
            count = cursor.fetchone()[0]
            report['database'][db_file]['records'] = count
            conn.close()
        except:
            pass

# Port availability
import socket
for port in [8501, 7860]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    report['ports'][str(port)] = {
        'in_use': result == 0,
        'status': 'occupied' if result == 0 else 'free'
    }
    sock.close()

# Large files
large_files = []
for root, dirs, files in os.walk('.'):
    # Skip virtual env and cache
    if '.venv' in root or '__pycache__' in root:
        continue
    for file in files:
        filepath = os.path.join(root, file)
        try:
            size_mb = os.path.getsize(filepath) / (1024**2)
            if size_mb > 10:  # Files larger than 10MB
                large_files.append({
                    'path': filepath,
                    'size_mb': round(size_mb, 2)
                })
        except:
            pass

report['files']['large_files'] = sorted(large_files, key=lambda x: x['size_mb'], reverse=True)[:10]
report['files']['total_python_files'] = len(list(Path('.').rglob('*.py')))
report['files']['total_pdf_files'] = len(list(Path('docs').rglob('*.pdf'))) if Path('docs').exists() else 0

# Git info
try:
    report['git']['branch'] = subprocess.check_output(['git', 'branch', '--show-current']).decode().strip()
    report['git']['commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()[:8]
    report['git']['tag'] = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0'], stderr=subprocess.DEVNULL).decode().strip()
except:
    pass

# Python version
report['system']['python'] = {
    'version': subprocess.check_output(['python3', '--version']).decode().strip(),
    'venv_active': 'VIRTUAL_ENV' in os.environ
}

# Check critical paths
critical_paths = [
    'web_interface.py',
    'app/api/main.py',
    'app/rag/pipeline.py',
    'modules/metadata_db.py',
    'config.py',
    '.env',
    'requirements.txt'
]

report['files']['critical_files'] = {
    path: os.path.exists(path) for path in critical_paths
}

# Performance benchmarks
import time
start = time.time()
from modules.metadata_db import MetadataDB
db = MetadataDB()
count = db.count_documents()
db_load_time = time.time() - start

report['performance'] = {
    'db_load_time_seconds': round(db_load_time, 3),
    'document_count': count
}

# Checklist summary
checks = {
    'disk_space_ok': report['disk']['free_gb'] > 1,
    'memory_ok': report['memory']['available_gb'] > 2,
    'ports_available': not report['ports']['8501']['in_use'] or not report['ports']['7860']['in_use'],
    'database_ok': all(report['database'].get(db, {}).get('exists', False) for db in ['metadata.db', 'everything_index.db']),
    'critical_files_ok': all(report['files']['critical_files'].values()),
    'python_ok': '3.12' in report['system']['python']['version'],
    'document_count_ok': report['performance']['document_count'] == 483
}

report['checklist'] = checks
report['all_checks_passed'] = all(checks.values())

# Save report
with open('reports/ops_check.json', 'w') as f:
    json.dump(report, f, indent=2)

# Print summary
print(f'📊 Operations Checklist Summary')
print('=' * 40)
for check, status in checks.items():
    icon = '✅' if status else '❌'
    print(f'{icon} {check}: {status}')
print('=' * 40)
print(f'Overall: {\"✅ PASSED\" if report[\"all_checks_passed\"] else \"❌ FAILED\"}')
print(f'\\n📄 Full report: reports/ops_check.json')
" 2>/dev/null

echo ""
cat reports/ops_check.json | python3 -m json.tool | head -50