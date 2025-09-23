#!/bin/bash
# =============================================================
# 🛑 모든 서비스 중지 스크립트
# =============================================================

echo "🛑 Stopping all AI-CHAT services..."
echo "===================================="

# PID 파일에서 읽기
if [ -f .pids/api.pid ]; then
    kill $(cat .pids/api.pid) 2>/dev/null && echo "✅ API Server stopped"
fi

if [ -f .pids/monitor.pid ]; then
    kill $(cat .pids/monitor.pid) 2>/dev/null && echo "✅ Monitor stopped"
fi

if [ -f .pids/web.pid ]; then
    kill $(cat .pids/web.pid) 2>/dev/null && echo "✅ Web Interface stopped"
fi

# 추가로 남은 프로세스 정리
pkill -f "streamlit" 2>/dev/null
pkill -f "api_server" 2>/dev/null
pkill -f "system_monitor" 2>/dev/null

# Docker 컨테이너 중지 (있는 경우)
docker compose down 2>/dev/null || true

echo ""
echo "✅ All services stopped successfully!"
echo "===================================="