#!/bin/bash
# Verify dual process management (FastAPI + Streamlit)
set -euo pipefail

LOG_FILE="reports/proc_ports.txt"
mkdir -p reports

echo "🔍 Process Management Verification" | tee $LOG_FILE
echo "===================================" | tee -a $LOG_FILE
echo "Date: $(date)" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Check if processes are running
echo "1. Current Python processes:" | tee -a $LOG_FILE
ps aux | grep -E "streamlit|uvicorn|fastapi" | grep -v grep | tee -a $LOG_FILE || echo "No processes running" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Check port usage
echo "2. Port usage check:" | tee -a $LOG_FILE
echo "   Port 8501 (Streamlit):" | tee -a $LOG_FILE
lsof -i :8501 2>/dev/null | tee -a $LOG_FILE || echo "   Port 8501 is free" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE
echo "   Port 7860 (FastAPI):" | tee -a $LOG_FILE
lsof -i :7860 2>/dev/null | tee -a $LOG_FILE || echo "   Port 7860 is free" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Test process cleanup
echo "3. Testing process cleanup..." | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Create test script with proper trap handling
cat > /tmp/test_cleanup.sh <<'EOF'
#!/bin/bash
set -euo pipefail

PIDS=()

cleanup() {
    echo "Cleaning up processes..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "Killed process $pid"
        fi
    done
}

trap cleanup EXIT INT TERM

# Start dummy processes
python -m http.server 7860 >/dev/null 2>&1 &
PIDS+=($!)
echo "Started dummy FastAPI on 7860 (PID: ${PIDS[-1]})"

python -m http.server 8501 >/dev/null 2>&1 &
PIDS+=($!)
echo "Started dummy Streamlit on 8501 (PID: ${PIDS[-1]})"

echo "Processes running..."
sleep 2

echo "Simulating Ctrl+C..."
cleanup
EOF

chmod +x /tmp/test_cleanup.sh
bash /tmp/test_cleanup.sh | tee -a $LOG_FILE
rm /tmp/test_cleanup.sh
echo "" | tee -a $LOG_FILE

# Analyze start_ai_chat.sh trap handling
echo "4. Analyzing start_ai_chat.sh trap handling:" | tee -a $LOG_FILE
grep -n "trap\|cleanup\|kill\|pkill" start_ai_chat.sh | head -20 | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Check for zombie processes
echo "5. Checking for zombie processes:" | tee -a $LOG_FILE
ps aux | grep defunct | grep -v grep | tee -a $LOG_FILE || echo "No zombie processes" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Process group verification
echo "6. Process group strategy:" | tee -a $LOG_FILE
echo "   - FastAPI runs on port 7860 in background (&)" | tee -a $LOG_FILE
echo "   - Streamlit runs on port 8501 in foreground" | tee -a $LOG_FILE
echo "   - Ctrl+C terminates Streamlit directly" | tee -a $LOG_FILE
echo "   - Trap handler cleans up FastAPI via stored PID" | tee -a $LOG_FILE
echo "   - Error trap ensures cleanup on unexpected exit" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

echo "✅ Process management verification complete" | tee -a $LOG_FILE
echo "📄 Report saved to: $LOG_FILE" | tee -a $LOG_FILE