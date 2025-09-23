#!/bin/bash
# =============================================================
# 🚀 AI-CHAT RAG 최적화 배포 스크립트
# =============================================================

set -e

echo "🚀 AI-CHAT RAG System - Optimized Deployment"
echo "============================================="

# 1. 환경 변수 설정 (메모리 최적화)
export LOW_VRAM=true
export N_CTX=4096
export N_BATCH=256
export MAX_TOKENS=512
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

echo "✅ Memory optimization settings applied"

# 2. 기존 프로세스 정리
echo "Cleaning up existing processes..."
pkill -f streamlit || true
docker compose down 2>/dev/null || true

# 3. 최적화된 시스템 시작
echo "Starting optimized system..."

# 최적화된 웹 인터페이스 실행
if [ -f "web_interface_optimized.py" ]; then
    echo "Using optimized web interface..."
    nohup streamlit run web_interface_optimized.py > streamlit.log 2>&1 &
else
    echo "Using standard web interface..."
    nohup streamlit run web_interface.py > streamlit.log 2>&1 &
fi

echo "✅ System started successfully!"
echo ""
echo "Access: http://localhost:8501"
echo "Logs: tail -f streamlit.log"