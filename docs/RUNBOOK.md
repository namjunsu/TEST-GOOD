# AI-CHAT Operations Runbook

## System Startup

### Normal Startup
```bash
# Method 1: Using launcher script
./start_ai_chat.sh

# Method 2: Using Makefile
make run

# Method 3: Manual startup
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
streamlit run web_interface.py --server.port 8501
```

### Startup Verification
1. Check FastAPI: http://localhost:7860/_healthz
2. Check Streamlit: http://localhost:8501
3. Verify logs: `tail -f logs/start_*.log`

## System Shutdown

### Graceful Shutdown
```bash
# Press Ctrl+C in terminal running start_ai_chat.sh
# Or manually:
pkill -f streamlit
pkill -f uvicorn
```

### Force Shutdown
```bash
# Kill all Python processes (use with caution)
pkill -9 -f python
```

## Common Issues and Solutions

### Issue: "config.py not found"
**Symptom**: System checker fails with config.py error

**Solution**:
```bash
# Restore config.py from git
git restore config.py

# Or create minimal config.py
echo "DOCS_DIR = 'docs'" > config.py
```

### Issue: "No module named quick_fix_rag"
**Symptom**: Import errors in RAG pipeline

**Solution**:
```bash
# This module has been removed
# System should use MetadataDB-based retrieval
# Check app/rag/retrievers/hybrid.py uses MetadataDB
```

### Issue: Port already in use
**Symptom**: "Address already in use" error

**Solution**:
```bash
# Find process using port
lsof -i :8501  # For Streamlit
lsof -i :7860  # For FastAPI

# Kill the process
kill -9 <PID>

# Or use different ports
AI_CHAT_PORT=8502 ./start_ai_chat.sh
```

### Issue: Database locked
**Symptom**: "database is locked" SQLite error

**Solution**:
```bash
# Remove lock files
rm metadata.db-shm metadata.db-wal
rm everything_index.db-shm everything_index.db-wal

# Verify database integrity
sqlite3 metadata.db "PRAGMA integrity_check;"
```

### Issue: No search results
**Symptom**: Queries return empty results

**Solution**:
```bash
# Check database content
python check_db_content.py

# Rebuild metadata if needed
python rebuild_metadata.py

# Verify known drafters
sqlite3 metadata.db "SELECT DISTINCT drafter FROM documents;"
```

### Issue: Memory/Performance issues
**Symptom**: System slow or unresponsive

**Solution**:
```bash
# Check memory usage
free -h
df -h

# Clear Python cache
make clean

# Restart with limited resources
ulimit -v 2000000  # Limit to 2GB
./start_ai_chat.sh
```

## Log Locations

| Component | Log Location | Purpose |
|-----------|-------------|---------|
| Startup | `logs/start_YYYYMMDD_HHMMSS.log` | System initialization |
| API | `logs/api_YYYYMMDD_HHMMSS.log` | FastAPI requests/errors |
| RAG | Python console output | Query processing |
| Database | No separate logs | Use SQLite CLI for debugging |

### Viewing Logs
```bash
# Latest startup log
ls -t logs/start_*.log | head -1 | xargs tail -f

# API logs
ls -t logs/api_*.log | head -1 | xargs tail -f

# All recent logs
tail -f logs/*.log
```

## Database Operations

### Backup Database
```bash
# Create backup with timestamp
cp metadata.db metadata.db.backup_$(date +%Y%m%d_%H%M%S)
cp everything_index.db everything_index.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Restore Database
```bash
# Restore from backup
cp metadata.db.backup_20251029_150000 metadata.db
cp everything_index.db.backup_20251029_150000 everything_index.db
```

### Database Queries
```bash
# Count documents
sqlite3 metadata.db "SELECT COUNT(*) FROM documents;"

# List drafters
sqlite3 metadata.db "SELECT DISTINCT drafter FROM documents ORDER BY drafter;"

# Find documents by year
sqlite3 metadata.db "SELECT filename FROM documents WHERE date LIKE '2024%';"

# Check index status
sqlite3 everything_index.db "SELECT COUNT(*) FROM documents;"
```

## Health Checks

### Quick Health Check
```bash
# Run built-in health check
python health_check.py

# Or use curl
curl http://localhost:7860/_healthz
curl http://localhost:8501/_stcore/health
```

### Comprehensive Check
```bash
# Run system checker
python utils/system_checker.py

# Run validation tests
python test_e2e_validation.py
python verify_golden_queries.py
```

## Performance Monitoring

### Resource Usage
```bash
# CPU and Memory
htop  # or top

# Disk usage
df -h
du -sh docs/

# Network connections
netstat -tlnp | grep -E "8501|7860"
```

### Query Performance
```bash
# Test query performance
python diagnose_qa_flow.py

# Monitor in logs
grep "total_ms" logs/*.log | tail -20
```

## Emergency Procedures

### Complete System Reset
```bash
# 1. Stop all services
pkill -f python

# 2. Clear all caches
make clean
rm -rf .streamlit/cache

# 3. Reset databases
git restore metadata.db everything_index.db

# 4. Restart
./start_ai_chat.sh
```

### Rollback Deployment
```bash
# Check available tags
git tag -l

# Rollback to previous version
git checkout pre-hygiene-20251029

# Restore databases if needed
git restore metadata.db everything_index.db

# Restart system
./start_ai_chat.sh
```

## Maintenance Tasks

### Daily
- Check disk space: `df -h`
- Review error logs: `grep ERROR logs/*.log`
- Verify service status: `curl http://localhost:8501`

### Weekly
- Backup databases
- Clear old logs: `find logs -name "*.log" -mtime +7 -delete`
- Run audit: `make audit`

### Monthly
- Update dependencies: `pip list --outdated`
- Rebuild indexes: `python rebuild_rag_indexes.py`
- Performance analysis: Review reports/

## Contact and Escalation

### System Issues
1. Check this runbook first
2. Review recent commits: `git log --oneline -10`
3. Check GitHub issues
4. Contact system administrator

### Data Issues
1. Verify with `check_db_content.py`
2. Try `fix_metadata_db.py`
3. Rebuild with `rebuild_metadata.py`
4. Restore from backup if needed