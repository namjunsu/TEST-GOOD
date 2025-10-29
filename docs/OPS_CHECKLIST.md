# AI-CHAT Operations Checklist

## Pre-Deployment Checklist

### Code Quality ✓
- [ ] All tests pass: `make test`
- [ ] Code formatted: `make fmt`
- [ ] No linting errors: `make lint`
- [ ] Type checking passes: `make type-check`
- [ ] Pre-commit hooks pass: `make pre-commit`

### Configuration ✓
- [ ] `.env` file configured with correct values
- [ ] `config.py` exists and valid
- [ ] Database files present:
  - [ ] `metadata.db` exists
  - [ ] `everything_index.db` exists
- [ ] Document directory exists: `docs/`

### Dependencies ✓
- [ ] Python version correct (3.12+): `python --version`
- [ ] Virtual environment activated: `.venv`
- [ ] All packages installed: `pip freeze | wc -l` (should be ~30+)
- [ ] No missing imports: `python -c "import app.rag.pipeline"`

### System Resources ✓
- [ ] Sufficient disk space (>1GB): `df -h .`
- [ ] Sufficient memory (>2GB free): `free -h`
- [ ] Required ports available:
  - [ ] Port 8501 (Streamlit): `lsof -i :8501`
  - [ ] Port 7860 (FastAPI): `lsof -i :7860`

### Data Integrity ✓
- [ ] Database readable: `sqlite3 metadata.db ".tables"`
- [ ] Document count correct: `sqlite3 metadata.db "SELECT COUNT(*) FROM documents;"` (should be 483)
- [ ] Known drafters loaded: `python -c "from modules.metadata_db import MetadataDB; print(len(MetadataDB().list_unique_drafters()))"`
- [ ] Sample query works: `python diagnose_qa_flow.py "2024년 문서"`

## Deployment Steps

### 1. Backup Current State
```bash
# Create deployment backup
mkdir -p backups/deploy_$(date +%Y%m%d)
cp metadata.db backups/deploy_$(date +%Y%m%d)/
cp everything_index.db backups/deploy_$(date +%Y%m%d)/
cp .env backups/deploy_$(date +%Y%m%d)/
```

### 2. Pull Latest Changes
```bash
git fetch origin
git pull origin main
```

### 3. Update Dependencies
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Run Migrations (if any)
```bash
# Check for migration scripts
ls scripts/migrate_*.py 2>/dev/null
# Run if exists
```

### 5. Start Services
```bash
./start_ai_chat.sh
```

### 6. Verify Deployment
- [ ] UI accessible: http://localhost:8501
- [ ] API docs accessible: http://localhost:7860/docs
- [ ] Health check passes: http://localhost:7860/_healthz
- [ ] Sample query returns results

## Post-Deployment Checklist

### Immediate (First 5 minutes) ✓
- [ ] Both services running (Streamlit + FastAPI)
- [ ] No error messages in startup log
- [ ] UI loads without errors
- [ ] Can perform basic search

### Short-term (First hour) ✓
- [ ] Memory usage stable: `free -h`
- [ ] CPU usage normal: `top`
- [ ] No error accumulation in logs: `grep ERROR logs/*.log | tail`
- [ ] Response times acceptable (<2s for queries)

### First Day ✓
- [ ] All query modes working:
  - [ ] LIST mode: "2024년 문서 목록"
  - [ ] Search: "최새름이 작성한 문서"
  - [ ] Structured: "year:2024 drafter:남준수"
- [ ] No database locks
- [ ] Log rotation working
- [ ] Disk space stable

## Rollback Procedure

### Quick Rollback (< 5 minutes)
```bash
# 1. Stop current services
pkill -f streamlit
pkill -f uvicorn

# 2. Checkout previous version
git checkout <previous-tag>

# 3. Restore databases
cp backups/deploy_*/metadata.db .
cp backups/deploy_*/everything_index.db .

# 4. Restart services
./start_ai_chat.sh
```

### Full Rollback (if needed)
```bash
# 1. Complete stop
make clean
pkill -f python

# 2. Restore from backup tag
git checkout pre-hygiene-20251029

# 3. Restore all data
cp backups/deploy_*/* .

# 4. Reinstall dependencies
pip install -r requirements.txt

# 5. Full restart
./start_ai_chat.sh
```

## Monitoring Points

### Key Metrics to Watch
| Metric | Normal Range | Alert Threshold | Check Command |
|--------|-------------|-----------------|---------------|
| Memory Usage | < 2GB | > 4GB | `free -h` |
| CPU Usage | < 50% | > 80% | `top` |
| Disk Space | > 1GB free | < 500MB | `df -h` |
| Response Time | < 2s | > 5s | Check logs |
| Error Rate | < 1% | > 5% | `grep ERROR logs/*.log \| wc -l` |
| Database Size | ~6MB | > 20MB | `du -sh *.db` |

### Log Patterns to Monitor
```bash
# Critical errors
grep -E "CRITICAL|FATAL" logs/*.log

# Database issues
grep -E "locked|corrupt|integrity" logs/*.log

# Memory issues
grep -E "MemoryError|OutOfMemory" logs/*.log

# Import errors
grep -E "ImportError|ModuleNotFound" logs/*.log
```

## Maintenance Windows

### Daily Tasks (2 minutes)
- [ ] Check service status
- [ ] Review error logs
- [ ] Verify disk space

### Weekly Tasks (10 minutes)
- [ ] Backup databases
- [ ] Clear old logs
- [ ] Run system audit: `make audit`
- [ ] Check for updates

### Monthly Tasks (30 minutes)
- [ ] Full system health check
- [ ] Performance analysis
- [ ] Update documentation
- [ ] Review and archive old backups
- [ ] Security updates check

## Emergency Contacts

### System Issues
- Primary: System Administrator
- Backup: DevOps Team
- Escalation: Engineering Manager

### Data Issues
- Primary: Data Team
- Backup: Database Administrator

### Business Issues
- Primary: Product Owner
- Backup: Business Analyst

## Quick Commands Reference

```bash
# Status checks
make audit                       # Full system audit
python health_check.py           # Quick health check
python diagnose_qa_flow.py       # Test QA flow

# Maintenance
make clean                       # Clean caches
make fmt                         # Format code
python rebuild_metadata.py       # Rebuild database

# Troubleshooting
sqlite3 metadata.db ".schema"   # Check DB schema
tail -f logs/*.log              # Watch all logs
python check_db_content.py      # Verify DB content

# Emergency
pkill -f python                 # Stop everything
git checkout <tag>              # Rollback version
./start_ai_chat.sh             # Restart system
```

## Success Criteria

A deployment is considered successful when:
1. ✅ All services start without errors
2. ✅ Health checks pass
3. ✅ Sample queries return expected results
4. ✅ No critical errors in first hour
5. ✅ Performance metrics within normal range
6. ✅ Users can access and use the system

---

*Last Updated: 2025-10-29*
*Next Review: Monthly*