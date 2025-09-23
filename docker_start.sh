#!/bin/bash
#
# Docker 컨테이너 시작 스크립트
# 모든 서비스를 순차적으로 시작
#

echo "🐳 AI-CHAT RAG System Starting in Docker..."
echo "==========================================="

# 환경 확인
echo "🔍 환경 확인 중..."
echo "  - Python: $(python3 --version)"
echo "  - GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'CPU mode')"
echo "  - Memory: $(free -h | grep Mem | awk '{print $2}')"

# 디렉토리 확인
echo "📁 디렉토리 확인 중..."
mkdir -p logs cache indexes models

# 모델 다운로드 확인
if [ ! -f "models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf" ]; then
    echo "📥 모델 다운로드 필요..."
    echo "  모델을 먼저 다운로드하세요:"
    echo "  python3 download_models.py"
fi

# 자동 인덱서 백그라운드 실행
echo "📚 자동 인덱서 시작..."
nohup python3 auto_indexer.py > logs/auto_indexer.log 2>&1 &
INDEXER_PID=$!

# 성능 모니터링 백그라운드 실행 (선택사항)
if [ "$ENABLE_MONITORING" = "true" ]; then
    echo "📊 성능 모니터링 시작..."
    nohup streamlit run performance_dashboard.py \
        --server.port 8502 \
        --server.address 0.0.0.0 \
        > logs/monitoring.log 2>&1 &
    MONITOR_PID=$!
fi

# 메인 웹 인터페이스 실행
echo "🚀 웹 인터페이스 시작..."
echo "==========================================="
echo "✅ 시스템 준비 완료!"
echo ""
echo "📌 접속 주소:"
echo "   - 메인: http://localhost:8501"
if [ "$ENABLE_MONITORING" = "true" ]; then
    echo "   - 모니터링: http://localhost:8502"
fi
echo ""
echo "📌 로그 확인:"
echo "   docker logs -f ai-chat-rag"
echo ""

# 메인 프로세스 실행 (포그라운드)
exec streamlit run web_interface.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true