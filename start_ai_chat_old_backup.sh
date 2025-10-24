#!/bin/bash
# =============================================
# AI-CHAT 간편 실행 스크립트 (시스템 검증 포함)
# =============================================

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
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
if [ -d ".venv" ]; then
    echo "✅ Python 가상환경 활성화..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "✅ Python 가상환경 활성화..."
    source venv/bin/activate
else
    echo -e "${RED}❌ 가상환경이 없습니다. 설치가 필요합니다!${NC}"
    exit 1
fi

# 시스템 검증 실행
echo ""
echo -e "${BLUE}🔍 시스템 검증 중...${NC}"
if python3 utils/system_checker.py; then
    echo -e "${GREEN}✅ 시스템 검증 완료${NC}"
else
    echo ""
    echo -e "${YELLOW}⚠️  경고 또는 오류가 발생했습니다.${NC}"
    echo -e "${YELLOW}   계속하려면 Enter, 취소하려면 Ctrl+C${NC}"
    read -p ""
fi

# 포트 포워딩 자동 설정
echo ""
echo -e "${CYAN}🔧 포트 포워딩 설정 중...${NC}"
powershell.exe -ExecutionPolicy Bypass -Command "
    # 기존 규칙 삭제
    netsh interface portproxy delete v4tov4 listenport=8501 listenaddress=0.0.0.0 2>\$null | Out-Null

    # WSL IP 가져오기
    \$wslIp = (wsl hostname -I).Trim().Split()[0]

    # 포트 포워딩 추가
    netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=\$wslIp | Out-Null

    # Windows IP 가져오기
    \$hostIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {\$_.IPAddress -notlike '127.*' -and \$_.IPAddress -notlike '169.*' -and \$_.IPAddress -notlike '192.168.*' -and \$_.InterfaceAlias -notlike '*WSL*'} | Select-Object -First 1).IPAddress

    Write-Host '✅ 포트 포워딩 설정 완료!' -ForegroundColor Green
    if (\$hostIp) {
        Write-Host \"   다른 PC 접속: http://\$hostIp:8501\" -ForegroundColor Cyan
    }
" 2>/dev/null

# Streamlit 실행
echo ""
echo -e "${GREEN}🚀 AI-CHAT 시작 중...${NC}"
echo ""
echo "================================="
echo "📌 브라우저에서 열기:"
echo "   이 PC: http://localhost:8501"
echo "   다른 PC: 위에 표시된 주소 사용"
echo "================================="
echo ""
echo "종료하려면: Ctrl + C"
echo ""

# 실행 (원래대로 루트의 web_interface.py 실행)
streamlit run web_interface.py --server.port 8501
