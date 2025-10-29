#!/bin/bash
# Verify health check endpoints
set -euo pipefail

LOG_FILE="reports/healthcheck.log"
mkdir -p reports

echo "🏥 Health Check Verification" | tee $LOG_FILE
echo "============================" | tee -a $LOG_FILE
echo "Date: $(date)" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Check if services are running first
FASTAPI_RUNNING=false
STREAMLIT_RUNNING=false

if lsof -i :7860 >/dev/null 2>&1; then
    FASTAPI_RUNNING=true
fi

if lsof -i :8501 >/dev/null 2>&1; then
    STREAMLIT_RUNNING=true
fi

echo "Service Status:" | tee -a $LOG_FILE
echo "- FastAPI (7860): $([ "$FASTAPI_RUNNING" = true ] && echo '✅ Running' || echo '❌ Not running')" | tee -a $LOG_FILE
echo "- Streamlit (8501): $([ "$STREAMLIT_RUNNING" = true ] && echo '✅ Running' || echo '❌ Not running')" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# FastAPI health check
echo "1. FastAPI Health Check:" | tee -a $LOG_FILE
if [ "$FASTAPI_RUNNING" = true ]; then
    echo "   GET http://localhost:7860/_healthz" | tee -a $LOG_FILE
    curl -s -o /dev/null -w "   Status: %{http_code}\n" http://localhost:7860/_healthz 2>/dev/null | tee -a $LOG_FILE || echo "   ❌ Failed" | tee -a $LOG_FILE

    echo "" | tee -a $LOG_FILE
    echo "   Response:" | tee -a $LOG_FILE
    curl -s http://localhost:7860/_healthz 2>/dev/null | tee -a $LOG_FILE || echo "   No response" | tee -a $LOG_FILE
    echo "" | tee -a $LOG_FILE

    # Try version endpoint
    echo "   GET http://localhost:7860/version" | tee -a $LOG_FILE
    curl -s http://localhost:7860/version 2>/dev/null | tee -a $LOG_FILE || echo "   Version endpoint not available" | tee -a $LOG_FILE
else
    echo "   ⚠️ FastAPI not running - start with ./start_ai_chat.sh" | tee -a $LOG_FILE
fi
echo "" | tee -a $LOG_FILE

# Streamlit health check
echo "2. Streamlit Health Check:" | tee -a $LOG_FILE
if [ "$STREAMLIT_RUNNING" = true ]; then
    echo "   GET http://localhost:8501/" | tee -a $LOG_FILE
    curl -s -o /dev/null -w "   Status: %{http_code}\n" http://localhost:8501/ 2>/dev/null | tee -a $LOG_FILE || echo "   ❌ Failed" | tee -a $LOG_FILE

    echo "" | tee -a $LOG_FILE
    echo "   GET http://localhost:8501/_stcore/health" | tee -a $LOG_FILE
    curl -s -o /dev/null -w "   Status: %{http_code}\n" http://localhost:8501/_stcore/health 2>/dev/null | tee -a $LOG_FILE || echo "   ❌ Failed" | tee -a $LOG_FILE
else
    echo "   ⚠️ Streamlit not running - start with ./start_ai_chat.sh" | tee -a $LOG_FILE
fi
echo "" | tee -a $LOG_FILE

# Database health check
echo "3. Database Health Check:" | tee -a $LOG_FILE
python3 -c "
from modules.metadata_db import MetadataDB
try:
    db = MetadataDB()
    count = db.count_documents()
    print(f'   ✅ Database accessible: {count} documents')
except Exception as e:
    print(f'   ❌ Database error: {e}')
" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Component health check
echo "4. Component Health Check:" | tee -a $LOG_FILE
python3 -c "
import sys
components = {
    'RAG Pipeline': 'app.rag.pipeline',
    'Query Router': 'app.rag.query_router',
    'Query Parser': 'app.rag.query_parser',
    'Metadata DB': 'modules.metadata_db',
    'Hybrid Retriever': 'app.rag.retrievers.hybrid'
}

for name, module in components.items():
    try:
        __import__(module)
        print(f'   ✅ {name}: OK')
    except ImportError as e:
        print(f'   ❌ {name}: {e}')
" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Git version info
echo "5. Version Information:" | tee -a $LOG_FILE
echo "   Git SHA: $(git rev-parse HEAD 2>/dev/null || echo 'Not available')" | tee -a $LOG_FILE
echo "   Git Branch: $(git branch --show-current 2>/dev/null || echo 'Not available')" | tee -a $LOG_FILE
echo "   Latest Tag: $(git describe --tags --abbrev=0 2>/dev/null || echo 'No tags')" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Summary
echo "📊 Summary:" | tee -a $LOG_FILE
if [ "$FASTAPI_RUNNING" = true ] && [ "$STREAMLIT_RUNNING" = true ]; then
    echo "✅ All services healthy" | tee -a $LOG_FILE
else
    echo "⚠️ Some services not running" | tee -a $LOG_FILE
    echo "   Run: ./start_ai_chat.sh" | tee -a $LOG_FILE
fi
echo "" | tee -a $LOG_FILE
echo "📄 Report saved to: $LOG_FILE" | tee -a $LOG_FILE