#!/bin/bash
#
# AI-CHAT 자동 시작 설정 스크립트
# 시스템 재부팅 시 자동으로 실행되도록 crontab 설정
#

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================="
echo "⚙️ AI-CHAT 자동 시작 설정"
echo "=================================="
echo ""

# 현재 디렉토리
CURRENT_DIR=$(pwd)

# crontab 항목 생성
CRON_ENTRY="@reboot cd $CURRENT_DIR && ./start_system.sh > logs/autostart.log 2>&1"
WATCHDOG_ENTRY="*/5 * * * * cd $CURRENT_DIR && ./system_watchdog.sh"
BACKUP_ENTRY="0 3 * * 0 cd $CURRENT_DIR && ./backup_system.sh"

# 현재 crontab 백업
echo "📋 현재 crontab 백업 중..."
crontab -l > /tmp/crontab_backup_$(date +%s).txt 2>/dev/null

# 이미 등록되어 있는지 확인
echo ""
echo "🔍 기존 설정 확인 중..."

if crontab -l 2>/dev/null | grep -q "start_system.sh"; then
    echo -e "${YELLOW}⚠️ 자동 시작이 이미 설정되어 있습니다${NC}"
else
    # 자동 시작 추가
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo -e "${GREEN}✅ 자동 시작 설정 완료${NC}"
fi

if crontab -l 2>/dev/null | grep -q "system_watchdog.sh"; then
    echo -e "${YELLOW}⚠️ 시스템 감시가 이미 설정되어 있습니다${NC}"
else
    # 시스템 감시 추가
    (crontab -l 2>/dev/null; echo "$WATCHDOG_ENTRY") | crontab -
    echo -e "${GREEN}✅ 시스템 감시 설정 완료 (5분마다)${NC}"
fi

if crontab -l 2>/dev/null | grep -q "backup_system.sh"; then
    echo -e "${YELLOW}⚠️ 자동 백업이 이미 설정되어 있습니다${NC}"
else
    # 자동 백업 추가
    (crontab -l 2>/dev/null; echo "$BACKUP_ENTRY") | crontab -
    echo -e "${GREEN}✅ 자동 백업 설정 완료 (매주 일요일 새벽 3시)${NC}"
fi

# 설정 확인
echo ""
echo "📋 현재 crontab 설정:"
echo "-----------------------------------"
crontab -l | grep -E "(start_system|watchdog|backup)" | while read line; do
    echo "  • $line"
done

echo ""
echo "=================================="
echo -e "${GREEN}✅ 자동화 설정 완료!${NC}"
echo "=================================="
echo ""
echo "📌 설정된 자동화:"
echo "  1. 시스템 재부팅 시 자동 시작"
echo "  2. 5분마다 프로세스 감시 및 자동 복구"
echo "  3. 매주 일요일 새벽 3시 자동 백업"
echo ""
echo "💡 설정 제거 방법:"
echo "   crontab -e (편집 후 해당 줄 삭제)"
echo ""