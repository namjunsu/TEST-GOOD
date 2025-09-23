#!/bin/bash
# =============================================================
# 🚀 AI-CHAT 모든 서비스 한번에 실행
# =============================================================

echo "🚀 AI-CHAT Complete System Launcher"
echo "===================================="
echo ""

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 1. 기존 프로세스 정리
echo -e "${YELLOW}1. Cleaning up existing processes...${NC}"
pkill -f "streamlit" 2>/dev/null || true
pkill -f "api_server" 2>/dev/null || true
pkill -f "system_monitor" 2>/dev/null || true
sleep 2

# 2. 환경 변수 설정
echo -e "${CYAN}2. Setting environment variables...${NC}"
export LOW_VRAM=true
export N_CTX=4096
export N_BATCH=256
export MAX_TOKENS=512
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
export CUDA_MODULE_LOADING=LAZY

# 3. API 서버 시작
echo -e "${GREEN}3. Starting API Server (port 8000)...${NC}"
nohup python3 api_server.py > logs/api_server.log 2>&1 &
API_PID=$!
echo "   API Server PID: $API_PID"
sleep 3

# 4. 모니터링 시스템 시작
echo -e "${GREEN}4. Starting System Monitor (port 8502)...${NC}"
nohup streamlit run system_monitor.py --server.port 8502 --server.address 0.0.0.0 > logs/monitor.log 2>&1 &
MONITOR_PID=$!
echo "   Monitor PID: $MONITOR_PID"
sleep 3

# 5. 메인 웹 인터페이스 시작
echo -e "${GREEN}5. Starting Main Web Interface (port 8501)...${NC}"
if [ -f "web_interface_optimized.py" ]; then
    echo "   Using optimized version..."
    nohup streamlit run web_interface_optimized.py --server.port 8501 --server.address 0.0.0.0 > logs/streamlit.log 2>&1 &
else
    echo "   Using standard version..."
    nohup streamlit run web_interface.py --server.port 8501 --server.address 0.0.0.0 > logs/streamlit.log 2>&1 &
fi
WEB_PID=$!
echo "   Web Interface PID: $WEB_PID"

# 6. 프로세스 확인
echo ""
echo -e "${CYAN}6. Verifying services...${NC}"
sleep 5

# API 헬스체크
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ API Server: Running${NC}"
else
    echo -e "   ❌ API Server: Failed"
fi

# 모니터링 체크
if curl -s http://localhost:8502 > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ System Monitor: Running${NC}"
else
    echo -e "   ❌ System Monitor: Failed"
fi

# 웹 인터페이스 체크
if curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Web Interface: Running${NC}"
else
    echo -e "   ❌ Web Interface: Failed"
fi

# 7. 시스템 정보
echo ""
echo "===================================="
echo -e "${GREEN}🎉 All Services Started!${NC}"
echo "===================================="
echo ""
echo "📌 Access Points:"
echo "   • Main Interface: http://localhost:8501"
echo "   • API Docs: http://localhost:8000/docs"
echo "   • System Monitor: http://localhost:8502"
echo ""
echo "📊 Process IDs:"
echo "   • API Server: $API_PID"
echo "   • Monitor: $MONITOR_PID"
echo "   • Web UI: $WEB_PID"
echo ""
echo "📝 Logs:"
echo "   • tail -f logs/api_server.log"
echo "   • tail -f logs/monitor.log"
echo "   • tail -f logs/streamlit.log"
echo ""
echo "🛑 To stop all services:"
echo "   • ./stop_all_services.sh"
echo ""
echo "===================================="

# PID 저장
echo "$API_PID" > .pids/api.pid
echo "$MONITOR_PID" > .pids/monitor.pid
echo "$WEB_PID" > .pids/web.pid

# 브라우저 자동 열기 (선택적)
if command -v xdg-open &> /dev/null; then
    sleep 2
    xdg-open http://localhost:8501 &
    xdg-open http://localhost:8000/docs &
    xdg-open http://localhost:8502 &
fi

echo -e "${GREEN}Ready to go! 🚀${NC}"