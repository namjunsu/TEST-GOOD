# AI-CHAT Operations Guide

**Version**: v2025.10.31-ops-baseline
**Environment**: WSL2, Python 3.12, RTX 4060
**Last Updated**: 2025-10-31

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Environment Variables Reference](#environment-variables-reference)
4. [Installation & Setup](#installation--setup)
5. [Start/Stop Procedures](#startstop-procedures)
6. [Health Checks](#health-checks)
7. [Log Management](#log-management)
8. [Indexing Operations](#indexing-operations)
9. [Monitoring & Metrics](#monitoring--metrics)
10. [Validation Routines](#validation-routines)
11. [Backup & Recovery](#backup--recovery)
12. [Service Level Objectives (SLO)](#service-level-objectives-slo)
13. [Troubleshooting](#troubleshooting)

---

## Overview

AI-CHAT is a RAG-based document Q&A system with:
- **Backend**: FastAPI (port 7860) serving `/ask`, `/metrics`, `/reindex` endpoints
- **Frontend**: Streamlit (port 8501) for user interaction
- **Storage**: SQLite databases (metadata.db, everything_index.db)
- **LLM**: llama-cpp-python with GGUF model support
- **Embeddings**: sentence-transformers for vector search
- **Search**: FAISS for similarity search + BM25 for keyword matching

### Key Features

- Automatic document ingestion from `docs/` directory
- Hybrid retrieval (semantic + keyword)
- Multi-mode responses (QA, SUMMARY, AUTO)
- Automatic chat format detection
- Preview & pagination in UI
- Reindex mutex for concurrency safety
- Structured logging with rotation

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│                  Streamlit (port 8501)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend API                             │
│                  FastAPI (port 7860)                         │
│  ┌─────────────────┬─────────────────┬─────────────────┐    │
│  │   /ask          │   /metrics      │   /reindex      │    │
│  └─────────────────┴─────────────────┴─────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  RAG Pipeline    │ │   Indexing       │ │   LLM Wrapper    │
│  - Stage 0       │ │   - Auto-scan    │ │   - Chat format  │
│  - Stage 1       │ │   - Mutex lock   │ │   - Context mgmt │
│  - Rerank (RRF)  │ │   - DB VACUUM    │ │   - Streaming    │
└──────────────────┘ └──────────────────┘ └──────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌─────────────────────────┬─────────────────────────────┐  │
│  │   metadata.db           │   everything_index.db       │  │
│  │   (file metadata)       │   (chunk vectors + BM25)    │  │
│  └─────────────────────────┴─────────────────────────────┘  │
│                                                              │
│                 File System: docs/                           │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Purpose | Location |
|-----------|---------|----------|
| **FastAPI** | REST API, request routing | `app/api/main.py` |
| **Streamlit** | User interface, file preview | `web_interface.py` |
| **RAG Pipeline** | Hybrid retrieval, reranking | `app/rag/pipeline.py` |
| **LLM Wrapper** | LLM inference, chat handling | `rag_system/llm_wrapper.py` |
| **Auto Indexer** | Background file scanning | `scripts/utils/auto_indexer.py` |
| **Logging** | Structured logs, rotation | `app/logging/config.py` |

---

## Environment Variables Reference

See `.env.sample` for complete template. Key variables:

### Model Configuration

```bash
# Chat format auto-detection (recommended: auto)
CHAT_FORMAT=auto

# Path to GGUF model file
MODEL_PATH=./models/your-model.gguf
```

### Directories

```bash
# Documents directory (auto-indexed)
DOCS_DIR=docs

# Data directory for internal files
DATA_DIR=data

# Incoming directory for new uploads
INCOMING_DIR=incoming
```

### Logging

```bash
# Log output directory
LOG_DIR=logs

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO
```

### Alerts

```bash
# Dry-run mode for alerts (true = no actual sending)
ALERTS_DRY_RUN=true

# Slack webhook URL for alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Advanced

```bash
# Server ports (defaults)
API_PORT=7860
UI_PORT=8501

# RAG parameters
TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Model parameters
TEMPERATURE=0.7
MAX_TOKENS=2048
CONTEXT_LENGTH=4096
```

**IMPORTANT**: Never commit `.env` to version control. Keep `.env.sample` updated with new variables.

---

## Installation & Setup

### Prerequisites

- WSL2 (Ubuntu 22.04+)
- Python 3.12+
- NVIDIA GPU with CUDA support (recommended: RTX 4060+)
- 16GB+ RAM
- 20GB+ disk space

### Initial Setup

```bash
# 1. Clone repository
git clone <repo-url> /home/wnstn4647/AI-CHAT
cd /home/wnstn4647/AI-CHAT

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment
cp .env.sample .env
nano .env  # Edit: MODEL_PATH, DOCS_DIR, etc.

# 5. Download GGUF model
mkdir -p models
# Place your .gguf model in models/ directory

# 6. Initialize databases
python scripts/utils/auto_indexer.py --force-rebuild

# 7. Install pre-commit hooks
make install
pre-commit install

# 8. Verify installation
make verify
```

### Verification

```bash
# Check dependencies
pip-audit  # Should show 0 vulnerabilities

# Check databases
sqlite3 metadata.db "PRAGMA integrity_check;"
sqlite3 everything_index.db "PRAGMA integrity_check;"

# Check metrics
curl -s http://localhost:7860/metrics | jq '.'
# Expected: stale_index_entries=0, fs_file_count≈index_file_count
```

---

## Start/Stop Procedures

### Start Services

#### Option 1: Using start script (recommended)

```bash
# Start backend + auto-indexer
bash start_ai_chat.sh
# Prompts: "Drop and rebuild index? (y/n)" → answer 'n' for normal start

# In separate terminal, start UI
streamlit run web_interface.py --server.port 8501 --server.headless true
```

#### Option 2: Manual start

```bash
# 1. Start backend
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 7860

# 2. Start auto-indexer (background)
nohup python scripts/utils/auto_indexer.py > logs/auto_indexer.log 2>&1 &

# 3. Start Streamlit
streamlit run web_interface.py --server.port 8501
```

### Stop Services

```bash
# Stop all AI-CHAT processes
pkill -f "uvicorn app.api.main"
pkill -f "streamlit run web_interface"
pkill -f "auto_indexer.py"

# Verify stopped
pgrep -a -f "ai-chat|uvicorn|streamlit" | grep -v grep
# Should return nothing
```

### Restart Services

```bash
# Safe restart (preserves index)
pkill -f "uvicorn app.api.main"
sleep 2
bash start_ai_chat.sh  # Answer 'n' to rebuild prompt
```

---

## Health Checks

### Backend API Health

```bash
# Health endpoint
curl -s http://localhost:7860/_healthz
# Expected: {"status": "ok"}

# Metrics endpoint
curl -s http://localhost:7860/metrics
# Expected: JSON with stale_index_entries, fs_file_count, etc.
```

### Database Health

```bash
# Integrity check
sqlite3 metadata.db "PRAGMA integrity_check;"
sqlite3 everything_index.db "PRAGMA integrity_check;"
# Expected: "ok"

# File count consistency
curl -s http://localhost:7860/metrics | jq '{stale: .stale_index_entries, fs: .fs_file_count, idx: .index_file_count}'
# Expected: stale=0, fs≈idx
```

### Reindex Mutex Health

```bash
# Check lock file
ls -la var/reindexing.lock 2>/dev/null
# Expected: File NOT FOUND (no reindex in progress)

# If lock exists for >30min, investigate:
ps aux | grep auto_indexer
# If process is dead, remove stale lock:
rm var/reindexing.lock
```

### Service Status

```bash
# Check running processes
pgrep -a -f "uvicorn|streamlit|auto_indexer"

# Check ports
ss -tulpn | grep -E '7860|8501'
# Expected:
# tcp   LISTEN  0.0.0.0:7860 (uvicorn)
# tcp   LISTEN  0.0.0.0:8501 (streamlit)
```

---

## Log Management

### Log Locations

| Log File | Purpose | Rotation |
|----------|---------|----------|
| `logs/ai-chat.log` | All logs (INFO+) | Daily, 7-day retention |
| `logs/ai-chat-error.log` | Errors only (ERROR+) | Daily, 7-day retention |
| `logs/auto_indexer.log` | Background indexing | Manual rotation |
| `/tmp/backend_*.log` | Temporary startup logs | Session-based |

### Log Schema

**Standard format** (non-structured):
```
[HH:MM:SS] LEVEL     logger_name: message
```

**Structured format** (JSON, when enabled):
```json
{
  "ts": "2025-10-31T12:34:56.789",
  "level": "INFO",
  "logger": "app.rag.pipeline",
  "message": "Query processed",
  "trace_id": "abc123...",
  "req_id": "xyz789",
  "mode": "QA",
  "has_code": true,
  "stage0_count": 10,
  "stage1_count": 5,
  "latency_ms": 8500,
  "coverage": 0.95
}
```

### Log Rotation

Configured in `app/logging/config.py`:
- **When**: Midnight (daily)
- **Retention**: 7 days (7 backups)
- **Format**: `ai-chat.log.YYYY-MM-DD`

### Viewing Logs

```bash
# Real-time tail
tail -f logs/ai-chat.log

# Filter by level
grep "ERROR" logs/ai-chat.log

# Filter by trace_id (for structured logs)
jq 'select(.trace_id=="abc123")' logs/ai-chat.log

# Recent errors
tail -100 logs/ai-chat-error.log
```

### Log Analysis

```bash
# Count requests by mode
jq -r '.mode' logs/ai-chat.log | sort | uniq -c

# Average latency
jq -r '.latency_ms' logs/ai-chat.log | awk '{s+=$1; n++} END {print s/n}'

# Coverage p95
jq -r '.coverage' logs/ai-chat.log | sort -n | awk 'BEGIN{c=0} {a[c++]=$1} END {print a[int(c*0.95)]}'
```

---

## Indexing Operations

### Automatic Indexing

**Background service** (`scripts/utils/auto_indexer.py`):
- Scans `DOCS_DIR` every 10 seconds
- Detects new/modified/deleted files
- Updates `metadata.db` and `everything_index.db`
- Uses Mutex lock (`var/reindexing.lock`) for concurrency safety

**Health metrics**:
```bash
curl -s http://localhost:7860/metrics | jq '{
  stale: .stale_index_entries,
  fs: .fs_file_count,
  idx: .index_file_count,
  last_reindex: .last_full_reindex_ts
}'
```

### Manual Reindex (Drop & Rebuild)

**Safe mode** (recommended):
```bash
# Via start script
bash start_ai_chat.sh
# Answer 'y' to rebuild prompt

# Or via UI
# Streamlit sidebar → "Drop & Rebuild Index" button
```

**Command-line**:
```bash
# Full rebuild
python scripts/utils/auto_indexer.py --force-rebuild

# With mutex check
if [ ! -f var/reindexing.lock ]; then
    python scripts/utils/auto_indexer.py --force-rebuild
else
    echo "Reindex already in progress"
fi
```

### Partial Reindex (Incremental)

**Add new files**:
```bash
# 1. Copy files to DOCS_DIR
cp new_docs/*.pdf docs/year_2025/

# 2. Auto-indexer detects within 10s
# Monitor logs:
tail -f logs/ai-chat.log | grep "New file detected"
```

**Remove files**:
```bash
# 1. Delete files from DOCS_DIR
rm docs/year_2025/obsolete.pdf

# 2. Auto-indexer purges from index within 10s
# Verify:
curl -s http://localhost:7860/metrics | jq '.stale_index_entries'
# Expected: 0
```

### Mutex Verification

**Check mutex state**:
```bash
# Lock file should NOT exist during normal operation
ls -la var/reindexing.lock 2>/dev/null && echo "REINDEXING" || echo "IDLE"

# If lock is stale (>30min old):
find var/reindexing.lock -mmin +30 2>/dev/null
# If found, check if indexer is actually running:
ps aux | grep auto_indexer
# If not running, remove stale lock:
rm var/reindexing.lock
```

### Database Optimization

**VACUUM** (reduce bloat):
```bash
# Backup first
cp metadata.db metadata.db.backup
cp everything_index.db everything_index.db.backup

# Run VACUUM
sqlite3 metadata.db "VACUUM; ANALYZE;"
sqlite3 everything_index.db "VACUUM; ANALYZE;"

# Verify size reduction
du -h metadata.db* everything_index.db*
```

**Frequency**: Monthly or after large bulk deletes

---

## Monitoring & Metrics

### /metrics Endpoint

**Schema**:
```json
{
  "stale_index_entries": 0,
  "fs_file_count": 488,
  "index_file_count": 488,
  "last_full_reindex_ts": "2025-10-31T14:52:08",
  "json_parse_failure_rate": 0.02,
  "coverage_p50": 0.85,
  "coverage_p95": 0.95,
  "stage0_hit_rate": 0.92,
  "reindex_mutex_state": "idle",
  "ui_action_count": {
    "preview": 145,
    "list": 89,
    "summary": 34
  }
}
```

**Key Metrics**:

| Metric | Description | Target | Alert If |
|--------|-------------|--------|----------|
| `stale_index_entries` | Files in index but missing on disk | 0 | > 0 |
| `fs_file_count` | Files in DOCS_DIR | - | - |
| `index_file_count` | Files indexed | ≈ fs_file_count | Diff > 5 |
| `last_full_reindex_ts` | Last full rebuild timestamp | - | > 7 days old |
| `json_parse_failure_rate` | Schema failure rate | < 0.015 | > 0.02 |
| `coverage_p50` | Median coverage | > 0.80 | < 0.80 |
| `coverage_p95` | 95th percentile coverage | > 0.90 | < 0.90 |
| `stage0_hit_rate` | Retrieval success rate | > 0.85 | < 0.85 |
| `reindex_mutex_state` | Mutex lock status | "idle" | "locked" > 30min |

### Alert Hooks

**Configuration** (`app/alerts.py`):
```python
# Alert conditions
ALERT_CONDITIONS = {
    'stale_index': lambda m: m['stale_index_entries'] > 0,
    'coverage_degraded': lambda m: m['coverage_p50'] < 0.80,
    'json_failures': lambda m: m['json_parse_failure_rate'] > 0.02,
    'mutex_stuck': lambda m: m['reindex_mutex_state'] == 'locked' and is_stale_lock(),
}

# Alert destinations
if not ALERTS_DRY_RUN:
    send_slack_alert(SLACK_WEBHOOK_URL, message)
```

**Testing alerts**:
```bash
# Dry-run mode (logs only)
export ALERTS_DRY_RUN=true
python -c "from app.alerts import check_and_alert; check_and_alert()"

# Production mode
export ALERTS_DRY_RUN=false
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
python -c "from app.alerts import check_and_alert; check_and_alert()"
```

### Performance Monitoring

**Response time**:
```bash
# /metrics endpoint latency (target: <50ms)
time curl -s http://localhost:7860/metrics > /dev/null

# /ask endpoint latency (logged in structured logs)
jq -r '.latency_ms' logs/ai-chat.log | awk '{s+=$1; n++} END {print "Avg: " s/n " ms"}'
```

**GPU usage**:
```bash
# Real-time monitoring
watch -n 1 nvidia-smi

# Log GPU stats
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits
```

---

## Validation Routines

### RAG Pipeline Validation

**Purpose**: Verify RAG quality metrics (Hit@K, MRR@K, citation rate, schema compliance)

**Run validation**:
```bash
# Full validation suite
python scripts/validate_rag.py \
    --results reports/askable_queries_validation_*.json \
    --output reports/RAG_QA_REPORT.md

# Expected AC:
# - Hit@3 ≥ 0.90
# - MRR@10 ≥ 0.80
# - Citation Rate = 1.00
# - Schema Failure ≤ 1.5%
# - Parsing Coverage ≥ 90%
```

**Frequency**: Weekly (automated via cron/systemd timer)

**Outputs**:
- `reports/RAG_QA_REPORT_YYYYMMDD.md` - Human-readable summary
- `reports/RAG_QA_REPORT_YYYYMMDD.json` - Machine-readable metrics

### Code Query Validation

**Purpose**: Test code-related queries with special handling

**Run validation**:
```bash
# Test code queries
python scripts/validate_codes.py

# Expected:
# - has_code detection accuracy
# - Code snippet extraction
# - Citation enforcement
```

**Frequency**: After code query feature changes

### Askable Queries Validation

**Purpose**: End-to-end validation with real user queries

**Run validation**:
```bash
# Set environment
set -a && source .env && set +a

# Run validation
python scripts/validate_askable_queries.py

# Expected: 95%+ success rate
```

**Frequency**: Before releases, monthly

**Outputs**:
- `reports/askable_queries_validation_YYYYMMDD_HHMMSS.md`
- `reports/askable_queries_validation_YYYYMMDD_HHMMSS.json`

---

## Backup & Recovery

### Backup Strategy

**What to backup**:
1. `metadata.db` - File metadata, doc-level info
2. `everything_index.db` - Chunk vectors, BM25 index
3. `.env` - Configuration (CRITICAL: keep secure)
4. `docs/` - Source documents (if not backed up elsewhere)

**Backup frequency**:
- Databases: Daily (automated)
- Config: On change
- Documents: Continuous (if using as source of truth)

### Backup Procedures

**Manual backup**:
```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup databases
cp metadata.db backups/$(date +%Y%m%d)/metadata.db
cp everything_index.db backups/$(date +%Y%m%d)/everything_index.db

# Backup config
cp .env backups/$(date +%Y%m%d)/.env

# Optional: Backup documents
tar -czf backups/$(date +%Y%m%d)/docs.tar.gz docs/
```

**Automated backup** (cron):
```bash
# Add to crontab: daily at 2AM
0 2 * * * /home/wnstn4647/AI-CHAT/scripts/backup_daily.sh
```

**Create `scripts/backup_daily.sh`**:
```bash
#!/bin/bash
BACKUP_DIR=/mnt/backups/ai-chat/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR
cp /home/wnstn4647/AI-CHAT/metadata.db $BACKUP_DIR/
cp /home/wnstn4647/AI-CHAT/everything_index.db $BACKUP_DIR/
cp /home/wnstn4647/AI-CHAT/.env $BACKUP_DIR/
find /mnt/backups/ai-chat -type d -mtime +30 -exec rm -rf {} \;  # 30-day retention
```

### Recovery Procedures

**Restore from backup**:
```bash
# 1. Stop services
pkill -f "uvicorn|streamlit|auto_indexer"

# 2. Verify backup integrity
sqlite3 backups/20251031/metadata.db "PRAGMA integrity_check;"
sqlite3 backups/20251031/everything_index.db "PRAGMA integrity_check;"

# 3. Restore databases
cp backups/20251031/metadata.db metadata.db
cp backups/20251031/everything_index.db everything_index.db

# 4. Verify metrics
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
sleep 5
curl -s http://localhost:7860/metrics | jq '{stale: .stale_index_entries, fs: .fs_file_count, idx: .index_file_count}'

# 5. If metrics look good, restart services
bash start_ai_chat.sh
```

**Rebuild from scratch** (if backup corrupted):
```bash
# 1. Remove corrupted databases
rm metadata.db everything_index.db

# 2. Full rebuild (requires docs/ to be intact)
python scripts/utils/auto_indexer.py --force-rebuild

# 3. Verify
curl -s http://localhost:7860/metrics | jq '.'
```

---

## Service Level Objectives (SLO)

### RAG Quality SLOs

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| **Hit@3** | ≥ 0.90 | Weekly validation | < 0.85 |
| **MRR@10** | ≥ 0.80 | Weekly validation | < 0.75 |
| **Citation Rate** | = 1.00 | Per query | < 0.95 |
| **JSON Schema Failure** | ≤ 1.5% | Per query | > 2.0% |
| **Parsing Coverage** | ≥ 90% | Per query | < 85% |

### Performance SLOs

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| **P50 Latency** | < 5s | Per query (logs) | > 8s |
| **P95 Latency** | < 12s | Per query (logs) | > 15s |
| **/metrics Response** | < 50ms | Health check | > 100ms |
| **Index Consistency** | 0 stale | `/metrics` | > 0 |

### Availability SLOs

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| **Uptime** | 99.5% | Monthly | < 99.0% |
| **Reindex Success** | 100% | Per reindex | Failure |
| **Auto-indexer Lag** | < 30s | File detection | > 60s |

### Quality Gates (Pre-Release)

Before merging to `main`:
- [ ] `pip-audit` → 0 vulnerabilities
- [ ] `pre-commit run -a` → All pass
- [ ] `scripts/validate_rag.py` → All AC met
- [ ] `curl http://localhost:7860/metrics` → `stale_index_entries=0`
- [ ] Manual UI/UX checklist → 100% pass

---

## Troubleshooting

### Issue: stale_index_entries > 0

**Symptoms**: `/metrics` shows `stale_index_entries > 0`

**Diagnosis**:
```bash
# Check what files are stale
sqlite3 metadata.db "SELECT filepath FROM files WHERE filepath NOT IN (SELECT filepath FROM files WHERE EXISTS (SELECT 1 FROM files WHERE filepath LIKE '%' || name));"
```

**Fix**:
```bash
# Option 1: Wait for auto-purge (next scan cycle)
tail -f logs/ai-chat.log | grep "purge"

# Option 2: Manual purge
python -c "from scripts.utils.auto_indexer import purge_missing_files; purge_missing_files()"

# Option 3: Full rebuild
python scripts/utils/auto_indexer.py --force-rebuild
```

---

### Issue: Mutex lock stuck

**Symptoms**: `var/reindexing.lock` exists for >30min, UI blocks reindex

**Diagnosis**:
```bash
# Check lock age
find var/reindexing.lock -mmin +30

# Check if indexer is running
ps aux | grep auto_indexer
```

**Fix**:
```bash
# If indexer is NOT running, remove stale lock
rm var/reindexing.lock

# If indexer IS running but stuck, kill and remove lock
pkill -f auto_indexer
rm var/reindexing.lock

# Verify metrics
curl -s http://localhost:7860/metrics | jq '.reindex_mutex_state'
```

---

### Issue: JSON schema failures > 2%

**Symptoms**: High `json_parse_failure_rate` in `/metrics`

**Diagnosis**:
```bash
# Check recent failures
grep "JSON parse failure" logs/ai-chat.log | tail -20

# Check which queries fail
jq -r 'select(.message | contains("fallback")) | .query' logs/ai-chat.log
```

**Fix**:
1. Review failure patterns (specific query types?)
2. Check if LLM model is appropriate for structured output
3. Consider increasing `TEMPERATURE` (lower = more deterministic)
4. Update prompt templates in `app/rag/summary_templates.py`

---

### Issue: Coverage degraded (p50 < 0.80)

**Symptoms**: Low `coverage_p50` in `/metrics`, poor answer quality

**Diagnosis**:
```bash
# Check stage0 retrieval counts
jq -r 'select(.stage0_count) | .stage0_count' logs/ai-chat.log | awk '{s+=$1; n++} END {print "Avg stage0: " s/n}'

# Check if embeddings are working
python -c "from rag_system.embedder import embed_text; print(embed_text('test')[:5])"
```

**Fix**:
1. Verify embedding model is loaded correctly
2. Check FAISS index integrity: `ls -lh everything_index.db`
3. Consider increasing `TOP_K` in `.env`
4. Rebuild index if corrupted: `python scripts/utils/auto_indexer.py --force-rebuild`

---

### Issue: High latency (p95 > 15s)

**Symptoms**: Slow responses, user complaints

**Diagnosis**:
```bash
# Check latency distribution
jq -r '.latency_ms' logs/ai-chat.log | sort -n | awk '{a[NR]=$1} END {print "P50: " a[int(NR*0.5)] " P95: " a[int(NR*0.95)]}'

# Check GPU usage
nvidia-smi
```

**Fix**:
1. GPU not used: Check CUDA installation, `nvidia-smi`
2. Model too large: Switch to smaller quantization (Q4_K_M → Q4_0)
3. Context too long: Reduce `CONTEXT_LENGTH`, `MAX_TOKENS` in `.env`
4. Too many chunks: Lower `TOP_K`, optimize stage1 filtering

---

### Issue: Backend won't start

**Symptoms**: `curl http://localhost:7860/_healthz` fails

**Diagnosis**:
```bash
# Check logs
tail -100 logs/ai-chat-error.log

# Check port in use
ss -tulpn | grep 7860

# Check model file
ls -lh $MODEL_PATH
```

**Fix**:
```bash
# Port already in use
pkill -f "uvicorn.*7860"
# Or change port: uvicorn app.api.main:app --port 7861

# Model not found
# Update MODEL_PATH in .env to correct path

# Database locked
rm metadata.db-shm metadata.db-wal
sqlite3 metadata.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

---

### Issue: UI shows "파일을 찾을 수 없습니다"

**Symptoms**: Preview button fails, error message in UI

**Diagnosis**:
```bash
# Check file actually exists
ls -la docs/year_2025/filename.pdf

# Check file permissions
stat docs/year_2025/filename.pdf
```

**Fix**:
```bash
# If file missing, restore from backup or remove from index
# If permissions wrong:
chmod 644 docs/year_2025/filename.pdf

# Force reindex to sync
python scripts/utils/auto_indexer.py --force-rebuild
```

---

### Issue: Validation failure (Hit@3 < 0.90)

**Symptoms**: Weekly validation reports failing SLOs

**Diagnosis**:
```bash
# Run detailed validation
python scripts/validate_rag.py \
    --results reports/askable_queries_validation_*.json \
    --output /tmp/debug_validation.md

# Review failures
grep "FAIL" /tmp/debug_validation.md
```

**Fix**:
1. **Retrieval issue**: Check embeddings, increase TOP_K
2. **Ranking issue**: Tune RRF weights in `app/rag/pipeline.py`
3. **Document quality**: Review failing queries, add missing docs
4. **Model issue**: Consider fine-tuning or model upgrade

---

### Common Error Codes

| Error | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError: metadata.db` | DB not initialized | Run `auto_indexer.py --force-rebuild` |
| `sqlite3.OperationalError: database is locked` | Concurrent access | Stop all processes, remove WAL files |
| `ModuleNotFoundError: llama_cpp` | Missing dependency | `pip install llama-cpp-python` |
| `CUDA out of memory` | Model too large | Reduce context length or use CPU |
| `JSONDecodeError` | Schema parsing failure | Logged as warning, fallback to free-form |

---

## Support & Contacts

- **Documentation**: `docs/` directory
- **Reports**: `reports/` directory
- **Scripts**: `scripts/` directory
- **Issue Tracking**: GitHub Issues (if applicable)
- **On-call**: TBD

---

**Generated**: 2025-10-31
**Version**: v2025.10.31-ops-baseline
**Maintainer**: AI-CHAT Operations Team
