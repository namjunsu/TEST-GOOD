#!/bin/bash
# Bootstrap test - Clean reproduction in 10 minutes
set -euo pipefail

LOG_FILE="reports/bootstrap_proof.txt"
mkdir -p reports

echo "🚀 AI-CHAT Bootstrap Test" | tee $LOG_FILE
echo "=========================" | tee -a $LOG_FILE
echo "Start: $(date)" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

START_TIME=$(date +%s)

# Step 1: Check prerequisites
echo "[1/6] Checking prerequisites..." | tee -a $LOG_FILE
python3 --version | tee -a $LOG_FILE
pip --version | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Step 2: Create virtual environment (if not exists)
if [ ! -d ".venv" ]; then
    echo "[2/6] Creating virtual environment..." | tee -a $LOG_FILE
    python3 -m venv .venv
else
    echo "[2/6] Virtual environment exists" | tee -a $LOG_FILE
fi
echo "" | tee -a $LOG_FILE

# Step 3: Activate and install dependencies
echo "[3/6] Installing dependencies..." | tee -a $LOG_FILE
source .venv/bin/activate
pip install -q -r requirements.txt 2>&1 | tail -5 | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Step 4: Configure environment
echo "[4/6] Configuring environment..." | tee -a $LOG_FILE
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env from .env.example" | tee -a $LOG_FILE
    else
        echo "AI_CHAT_PORT=8501" > .env
        echo "AI_CHAT_HOST=0.0.0.0" >> .env
        echo "Created minimal .env" | tee -a $LOG_FILE
    fi
else
    echo ".env exists" | tee -a $LOG_FILE
fi
echo "" | tee -a $LOG_FILE

# Step 5: Run tests
echo "[5/6] Running smoke tests..." | tee -a $LOG_FILE
python tests/test_smoke.py 2>&1 | grep -E "Results:|All smoke tests" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Step 6: Check if system can start (without actually starting)
echo "[6/6] Verifying system components..." | tee -a $LOG_FILE
python -c "
import sys
try:
    import streamlit
    import uvicorn
    from app.rag.pipeline import RAGPipeline
    from modules.metadata_db import MetadataDB
    print('✅ All components importable')
except ImportError as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
" | tee -a $LOG_FILE

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "" | tee -a $LOG_FILE
echo "=========================" | tee -a $LOG_FILE
echo "End: $(date)" | tee -a $LOG_FILE
echo "Total time: ${ELAPSED} seconds ($(($ELAPSED / 60)) minutes)" | tee -a $LOG_FILE

if [ $ELAPSED -lt 600 ]; then
    echo "✅ Bootstrap completed in under 10 minutes!" | tee -a $LOG_FILE
else
    echo "⚠️ Bootstrap took longer than 10 minutes" | tee -a $LOG_FILE
fi

echo "" | tee -a $LOG_FILE
echo "📊 Summary:" | tee -a $LOG_FILE
echo "- Prerequisites: ✅" | tee -a $LOG_FILE
echo "- Environment: ✅" | tee -a $LOG_FILE
echo "- Dependencies: ✅" | tee -a $LOG_FILE
echo "- Tests: ✅" | tee -a $LOG_FILE
echo "- Components: ✅" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE
echo "✅ System ready to run with: ./start_ai_chat.sh" | tee -a $LOG_FILE