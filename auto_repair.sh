#!/bin/bash
#
# AI-CHAT 자동 복구 스크립트
# 시스템 문제 자동 진단 및 복구
#

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================="
echo "🔧 AI-CHAT 시스템 자동 복구"
echo "=================================="
echo ""

FIXED_COUNT=0
ISSUES_COUNT=0

# 1. 프로세스 체크
echo "1️⃣ 프로세스 상태 확인..."

check_and_fix_process() {
    local process_name=$1
    local friendly_name=$2

    if ! pgrep -f "$process_name" > /dev/null; then
        echo -e "${RED}❌ $friendly_name 중지됨${NC}"
        ISSUES_COUNT=$((ISSUES_COUNT + 1))

        echo "   복구 시도 중..."
        if [ "$friendly_name" == "웹 인터페이스" ]; then
            nohup streamlit run web_interface.py > logs/web_interface.log 2>&1 &
        elif [ "$friendly_name" == "자동 인덱싱" ]; then
            nohup python3 auto_indexer.py > logs/auto_indexer.log 2>&1 &
        elif [ "$friendly_name" == "OCR 모니터" ]; then
            nohup python3 auto_ocr_monitor.py > logs/ocr_monitor.log 2>&1 &
        fi

        sleep 3
        if pgrep -f "$process_name" > /dev/null; then
            echo -e "${GREEN}   ✅ $friendly_name 복구 성공${NC}"
            FIXED_COUNT=$((FIXED_COUNT + 1))
        else
            echo -e "${RED}   ❌ $friendly_name 복구 실패${NC}"
        fi
    else
        echo -e "${GREEN}✅ $friendly_name 정상${NC}"
    fi
}

check_and_fix_process "streamlit run web_interface.py" "웹 인터페이스"
check_and_fix_process "auto_indexer.py" "자동 인덱싱"
check_and_fix_process "auto_ocr_monitor.py" "OCR 모니터"

# 2. 디렉토리 구조 체크
echo ""
echo "2️⃣ 디렉토리 구조 확인..."

check_and_create_dir() {
    local dir=$1
    if [ ! -d "$dir" ]; then
        echo -e "${YELLOW}⚠️ $dir 디렉토리 없음${NC}"
        ISSUES_COUNT=$((ISSUES_COUNT + 1))
        mkdir -p "$dir"
        echo -e "${GREEN}   ✅ $dir 생성됨${NC}"
        FIXED_COUNT=$((FIXED_COUNT + 1))
    fi
}

check_and_create_dir "logs"
check_and_create_dir "docs"
check_and_create_dir "backups"
check_and_create_dir "rag_system/indexes"

# 3. 권한 체크
echo ""
echo "3️⃣ 파일 권한 확인..."

for script in *.sh; do
    if [ -f "$script" ] && [ ! -x "$script" ]; then
        echo -e "${YELLOW}⚠️ $script 실행 권한 없음${NC}"
        ISSUES_COUNT=$((ISSUES_COUNT + 1))
        chmod +x "$script"
        echo -e "${GREEN}   ✅ 실행 권한 추가됨${NC}"
        FIXED_COUNT=$((FIXED_COUNT + 1))
    fi
done

# 4. 메타데이터 무결성 체크
echo ""
echo "4️⃣ 메타데이터 무결성 확인..."

if [ -f "metadata.db" ]; then
    if ! python3 -c "import sqlite3; conn=sqlite3.connect('metadata.db'); conn.close()" 2>/dev/null; then
        echo -e "${RED}❌ 메타데이터 DB 손상${NC}"
        ISSUES_COUNT=$((ISSUES_COUNT + 1))

        # 백업에서 복원 시도
        LATEST_BACKUP=$(ls -t backups/*.tar.gz 2>/dev/null | head -1)
        if [ -n "$LATEST_BACKUP" ]; then
            echo "   최근 백업에서 복원 시도..."
            # 복원 로직
            echo -e "${YELLOW}   ⚠️ 수동 복원 필요: ./restore_backup.sh $LATEST_BACKUP${NC}"
        else
            echo "   메타데이터 재구축..."
            python3 build_metadata_db.py
            FIXED_COUNT=$((FIXED_COUNT + 1))
        fi
    else
        echo -e "${GREEN}✅ 메타데이터 DB 정상${NC}"
    fi
fi

# 5. 로그 정리
echo ""
echo "5️⃣ 로그 파일 정리..."

LOG_SIZE=$(du -sh logs 2>/dev/null | cut -f1)
if [ -d "logs" ]; then
    # 30일 이상된 로그 압축
    find logs -name "*.log" -mtime +30 -exec gzip {} \; 2>/dev/null

    # 90일 이상된 압축 로그 삭제
    DELETED=$(find logs -name "*.gz" -mtime +90 -delete -print 2>/dev/null | wc -l)
    if [ $DELETED -gt 0 ]; then
        echo -e "${GREEN}✅ 오래된 로그 $DELETED개 정리됨${NC}"
        FIXED_COUNT=$((FIXED_COUNT + 1))
    fi
fi

# 6. 메모리 체크
echo ""
echo "6️⃣ 메모리 상태 확인..."

MEM_USAGE=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
if [ $MEM_USAGE -gt 85 ]; then
    echo -e "${YELLOW}⚠️ 메모리 사용률 높음: ${MEM_USAGE}%${NC}"
    ISSUES_COUNT=$((ISSUES_COUNT + 1))

    # 캐시 정리
    sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null 2>&1

    NEW_MEM=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
    echo -e "${GREEN}   ✅ 캐시 정리 완료 (${MEM_USAGE}% → ${NEW_MEM}%)${NC}"
    FIXED_COUNT=$((FIXED_COUNT + 1))
else
    echo -e "${GREEN}✅ 메모리 사용률 정상: ${MEM_USAGE}%${NC}"
fi

# 결과 요약
echo ""
echo "=================================="
if [ $ISSUES_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ 시스템 정상 - 문제 없음${NC}"
else
    echo "📊 복구 결과:"
    echo "   • 발견된 문제: $ISSUES_COUNT개"
    echo "   • 복구 성공: $FIXED_COUNT개"
    echo "   • 복구 실패: $((ISSUES_COUNT - FIXED_COUNT))개"
fi
echo "=================================="

# 복구 실패한 항목이 있으면 전체 재시작 권장
if [ $((ISSUES_COUNT - FIXED_COUNT)) -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}💡 일부 문제를 복구하지 못했습니다.${NC}"
    echo "   전체 재시작을 권장합니다: ./restart_system.sh"
fi

echo ""