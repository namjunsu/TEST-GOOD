#!/bin/bash

#
# AI-CHAT RAG System - 실시간 모니터링 스크립트
# 시스템 상태를 실시간으로 모니터링
#

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 모니터링 간격 (초)
INTERVAL=${1:-5}

# 헤더 출력
print_header() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       AI-CHAT RAG System - 실시간 모니터링          ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# CPU 및 메모리 사용량
show_resources() {
    echo -e "${BLUE}📊 시스템 리소스:${NC}"
    echo "─────────────────────────────────"

    # CPU 사용률
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    echo -e "CPU: ${GREEN}${CPU_USAGE}%${NC}"

    # 메모리 사용량
    MEM_USAGE=$(free -h | awk '/^Mem:/ {printf "사용: %s / 전체: %s (%.1f%%)", $3, $2, ($3/$2)*100}')
    echo -e "메모리: ${GREEN}${MEM_USAGE}${NC}"

    # GPU 사용량 (있는 경우)
    if command -v nvidia-smi &> /dev/null; then
        GPU_USAGE=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits | head -1)
        echo -e "GPU: ${GREEN}${GPU_USAGE}${NC}"
    fi

    echo ""
}

# Docker 컨테이너 상태
show_containers() {
    echo -e "${BLUE}🐳 Docker 컨테이너:${NC}"
    echo "─────────────────────────────────"

    if command -v docker &> /dev/null; then
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "ai-chat|rag"
    else
        echo "Docker가 설치되지 않았습니다"
    fi

    echo ""
}

# 서비스 헬스체크
check_services() {
    echo -e "${BLUE}🔍 서비스 상태:${NC}"
    echo "─────────────────────────────────"

    # 메인 서비스
    if curl -sf http://localhost:8501/_stcore/health &>/dev/null; then
        echo -e "웹 인터페이스: ${GREEN}● 정상${NC}"
    else
        echo -e "웹 인터페이스: ${RED}● 오프라인${NC}"
    fi

    # 모니터링 대시보드
    if curl -sf http://localhost:8502 &>/dev/null; then
        echo -e "모니터링: ${GREEN}● 정상${NC}"
    else
        echo -e "모니터링: ${YELLOW}● 오프라인${NC}"
    fi

    # Redis
    if docker exec ai-chat-redis redis-cli ping &>/dev/null; then
        echo -e "Redis 캐시: ${GREEN}● 정상${NC}"
    else
        echo -e "Redis 캐시: ${YELLOW}● 오프라인${NC}"
    fi

    echo ""
}

# 로그 미리보기
show_recent_logs() {
    echo -e "${BLUE}📝 최근 로그:${NC}"
    echo "─────────────────────────────────"

    if [ -f "logs/system.log" ]; then
        tail -5 logs/system.log 2>/dev/null | sed 's/^/  /'
    else
        docker compose logs --tail=5 2>/dev/null | sed 's/^/  /'
    fi

    echo ""
}

# 성능 메트릭
show_metrics() {
    echo -e "${BLUE}📈 성능 메트릭:${NC}"
    echo "─────────────────────────────────"

    # 응답 시간 (로그에서 추출)
    if [ -f "logs/system.log" ]; then
        AVG_TIME=$(grep "응답 생성:" logs/system.log 2>/dev/null | tail -10 | grep -oP '\d+\.\d+초' | sed 's/초//' | awk '{sum+=$1} END {if(NR>0) printf "%.2f", sum/NR; else print "N/A"}')
        echo -e "평균 응답 시간: ${GREEN}${AVG_TIME}초${NC}"
    fi

    # 캐시 히트율
    if [ -f "cache/stats.json" ]; then
        HIT_RATE=$(jq -r '.hit_rate' cache/stats.json 2>/dev/null || echo "N/A")
        echo -e "캐시 히트율: ${GREEN}${HIT_RATE}%${NC}"
    fi

    # 처리된 문서 수
    DOC_COUNT=$(find docs -name "*.pdf" 2>/dev/null | wc -l)
    echo -e "문서 수: ${GREEN}${DOC_COUNT}개${NC}"

    echo ""
}

# 알림
show_alerts() {
    echo -e "${BLUE}⚠️  알림:${NC}"
    echo "─────────────────────────────────"

    ALERT_COUNT=0

    # CPU 과부하 체크
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 | cut -d'.' -f1)
    if [ "$CPU_USAGE" -gt 80 ]; then
        echo -e "${YELLOW}• CPU 사용률이 높습니다 (${CPU_USAGE}%)${NC}"
        ALERT_COUNT=$((ALERT_COUNT + 1))
    fi

    # 메모리 부족 체크
    MEM_FREE=$(free -m | awk '/^Mem:/ {print $4}')
    if [ "$MEM_FREE" -lt 1024 ]; then
        echo -e "${YELLOW}• 여유 메모리가 부족합니다 (${MEM_FREE}MB)${NC}"
        ALERT_COUNT=$((ALERT_COUNT + 1))
    fi

    # 디스크 공간 체크
    DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$DISK_USAGE" -gt 90 ]; then
        echo -e "${RED}• 디스크 공간이 부족합니다 (${DISK_USAGE}% 사용중)${NC}"
        ALERT_COUNT=$((ALERT_COUNT + 1))
    fi

    if [ "$ALERT_COUNT" -eq 0 ]; then
        echo -e "${GREEN}• 모든 시스템이 정상입니다${NC}"
    fi

    echo ""
}

# 메인 루프
main() {
    # Ctrl+C 핸들러
    trap 'echo -e "\n${YELLOW}모니터링 종료${NC}"; exit 0' INT

    while true; do
        print_header

        # 현재 시간
        echo -e "${CYAN}🕐 $(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo ""

        # 각 섹션 표시
        show_resources
        show_containers
        check_services
        show_recent_logs
        show_metrics
        show_alerts

        # 하단 정보
        echo "─────────────────────────────────────────────────────"
        echo -e "${CYAN}새로고침 간격: ${INTERVAL}초 | 종료: Ctrl+C${NC}"

        # 대기
        sleep "$INTERVAL"
    done
}

# 실행
main