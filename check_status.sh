#!/bin/bash
# =============================================
# AI-CHAT 상태 모니터링
# =============================================

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      🔍 AI-CHAT 시스템 상태 점검      ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "🕐 점검 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 프로세스 상태
echo -e "${YELLOW}1️⃣  프로그램 상태${NC}"
echo "─────────────────"
if pgrep -f streamlit > /dev/null; then
    PID=$(pgrep -f streamlit | head -1)
    echo -e "   상태: ${GREEN}✅ 실행 중${NC}"
    echo "   PID: $PID"
    echo "   URL: http://localhost:8501"
else
    echo -e "   상태: ${RED}❌ 실행 안 됨${NC}"
    echo "   시작: ~/start_ai_chat.sh"
fi
echo ""

# 2. 메모리 사용량
echo -e "${YELLOW}2️⃣  메모리 사용량${NC}"
echo "─────────────────"
MEM_INFO=$(free -h | grep Mem)
TOTAL_MEM=$(echo $MEM_INFO | awk '{print $2}')
USED_MEM=$(echo $MEM_INFO | awk '{print $3}')
FREE_MEM=$(echo $MEM_INFO | awk '{print $4}')
PERCENT=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100}')

echo "   전체: $TOTAL_MEM"
echo "   사용: $USED_MEM ($PERCENT%)"
echo "   여유: $FREE_MEM"

if (( $(echo "$PERCENT > 80" | bc -l) )); then
    echo -e "   ${RED}⚠️  메모리 부족 경고!${NC}"
fi
echo ""

# 3. 디스크 공간
echo -e "${YELLOW}3️⃣  디스크 공간${NC}"
echo "─────────────────"
DISK_INFO=$(df -h /home | tail -1)
DISK_TOTAL=$(echo $DISK_INFO | awk '{print $2}')
DISK_USED=$(echo $DISK_INFO | awk '{print $3}')
DISK_FREE=$(echo $DISK_INFO | awk '{print $4}')
DISK_PERCENT=$(echo $DISK_INFO | awk '{print $5}')

echo "   전체: $DISK_TOTAL"
echo "   사용: $DISK_USED ($DISK_PERCENT)"
echo "   여유: $DISK_FREE"

if [ "${DISK_PERCENT%\%}" -gt 80 ]; then
    echo -e "   ${RED}⚠️  디스크 공간 부족!${NC}"
fi
echo ""

# 4. GPU 상태 (있는 경우)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${YELLOW}4️⃣  GPU 상태${NC}"
    echo "─────────────────"
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader)
    echo "   $GPU_INFO" | sed 's/,/\n   /g'
    echo ""
fi

# 5. 파일 상태
echo -e "${YELLOW}5️⃣  데이터 파일${NC}"
echo "─────────────────"
if [ -d "/home/wnstn4647/AI-CHAT" ]; then
    cd /home/wnstn4647/AI-CHAT
    MODEL_SIZE=$(du -sh models 2>/dev/null | cut -f1 || echo "없음")
    PDF_COUNT=$(find docs -name "*.pdf" 2>/dev/null | wc -l || echo "0")
    CACHE_SIZE=$(du -sh cache 2>/dev/null | cut -f1 || echo "없음")
    LOG_SIZE=$(du -sh logs 2>/dev/null | cut -f1 || echo "없음")

    echo "   모델: $MODEL_SIZE"
    echo "   PDF: ${PDF_COUNT}개 문서"
    echo "   캐시: $CACHE_SIZE"
    echo "   로그: $LOG_SIZE"
else
    echo -e "   ${RED}AI-CHAT 폴더 없음${NC}"
fi
echo ""

# 6. 최근 활동
echo -e "${YELLOW}6️⃣  최근 활동${NC}"
echo "─────────────────"
if [ -f "/home/wnstn4647/AI-CHAT/logs/system.log" ]; then
    echo "   최근 로그 (마지막 3줄):"
    tail -3 /home/wnstn4647/AI-CHAT/logs/system.log 2>/dev/null | sed 's/^/   /'
else
    echo "   로그 파일 없음"
fi
echo ""

# 7. 네트워크 상태
echo -e "${YELLOW}7️⃣  네트워크 포트${NC}"
echo "─────────────────"
if netstat -tuln 2>/dev/null | grep -q ":8501"; then
    echo -e "   포트 8501: ${GREEN}✅ 열림${NC}"
    LOCAL_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+' | grep -v 127.0.0.1 | head -1)
    echo "   로컬 접속: http://localhost:8501"
    echo "   네트워크 접속: http://$LOCAL_IP:8501"
else
    echo -e "   포트 8501: ${RED}❌ 닫힘${NC}"
fi
echo ""

# 요약
echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║            📊 요약 정보               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"

if pgrep -f streamlit > /dev/null; then
    echo -e " ${GREEN}✅ 시스템 정상 작동 중${NC}"
    echo ""
    echo " 🌐 브라우저에서 열기:"
    echo "    http://localhost:8501"
else
    echo -e " ${YELLOW}⚠️  시스템이 실행되지 않았습니다${NC}"
    echo ""
    echo " 시작하려면:"
    echo "    ~/start_ai_chat.sh"
fi
echo ""