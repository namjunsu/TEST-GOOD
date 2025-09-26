#!/bin/bash
# =============================================
# AI-CHAT 간편 실행 스크립트
# =============================================

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

clear
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}    🤖 AI-CHAT 시작하기 🤖     ${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""

# 프로그램 이미 실행 중인지 확인
if pgrep -f streamlit > /dev/null; then
    echo -e "${YELLOW}⚠️  AI-CHAT이 이미 실행 중입니다!${NC}"
    echo ""
    echo "브라우저에서 열기: http://localhost:8501"
    echo ""
    read -p "재시작하시겠습니까? (y/n): " restart
    if [ "$restart" = "y" ]; then
        echo "프로그램 종료 중..."
        pkill -f streamlit
        sleep 2
    else
        exit 0
    fi
fi

# AI-CHAT 폴더로 이동
cd /home/wnstn4647/AI-CHAT || {
    echo -e "${RED}❌ AI-CHAT 폴더를 찾을 수 없습니다!${NC}"
    exit 1
}

# 가상환경 활성화
if [ -d "venv" ]; then
    echo "✅ Python 가상환경 활성화..."
    source venv/bin/activate
else
    echo -e "${RED}❌ 가상환경이 없습니다. 설치가 필요합니다!${NC}"
    exit 1
fi

# Streamlit 실행
echo ""
echo -e "${GREEN}🚀 AI-CHAT 시작 중...${NC}"
echo ""
echo "================================="
echo "📌 브라우저에서 열기:"
echo "   http://localhost:8501"
echo "================================="
echo ""
echo "종료하려면: Ctrl + C"
echo ""

# 실행
streamlit run web_interface.py