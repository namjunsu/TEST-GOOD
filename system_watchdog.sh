#!/bin/bash
#
# AI-CHAT 시스템 감시 및 자동 복구 스크립트
# 5분마다 실행되어 프로세스 상태 확인 및 자동 재시작
#

LOG_FILE="logs/watchdog.log"
mkdir -p logs

# 로그 함수
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> $LOG_FILE
}

# 프로세스 체크 함수
check_process() {
    local process_name=$1
    local pid_file=$2
    local start_command=$3

    if [ -f "$pid_file" ]; then
        PID=$(cat $pid_file)
        if ! ps -p $PID > /dev/null 2>&1; then
            log "❌ $process_name (PID: $PID) 중지됨. 재시작 시도..."
            eval $start_command
            sleep 3

            # 재시작 확인
            if pgrep -f "$process_name" > /dev/null; then
                NEW_PID=$(pgrep -f "$process_name" | head -1)
                echo $NEW_PID > $pid_file
                log "✅ $process_name 재시작 성공 (새 PID: $NEW_PID)"
            else
                log "🚨 $process_name 재시작 실패!"
            fi
        fi
    else
        # PID 파일이 없지만 프로세스가 죽어있을 수 있음
        if ! pgrep -f "$process_name" > /dev/null; then
            log "⚠️ $process_name 실행되지 않음. 시작 시도..."
            eval $start_command
            sleep 3

            if pgrep -f "$process_name" > /dev/null; then
                NEW_PID=$(pgrep -f "$process_name" | head -1)
                echo $NEW_PID > $pid_file
                log "✅ $process_name 시작 성공 (PID: $NEW_PID)"
            fi
        fi
    fi
}

# 메모리 체크
check_memory() {
    MEM_USAGE=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
    if [ $MEM_USAGE -gt 90 ]; then
        log "⚠️ 메모리 사용률 높음: ${MEM_USAGE}%"

        # 캐시 정리
        sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null

        # 심각한 경우 재시작
        if [ $MEM_USAGE -gt 95 ]; then
            log "🚨 메모리 임계값 초과! 시스템 재시작..."
            ./restart_system.sh
        fi
    fi
}

# 디스크 체크
check_disk() {
    DISK_USAGE=$(df /home | awk 'NR==2 {print int($5)}')
    if [ $DISK_USAGE -gt 90 ]; then
        log "⚠️ 디스크 사용률 높음: ${DISK_USAGE}%"

        # 오래된 로그 정리
        find logs -name "*.log" -mtime +30 -delete 2>/dev/null
        find logs -name "*.gz" -mtime +90 -delete 2>/dev/null
    fi
}

# 메인 감시 로직
log "🔍 시스템 감시 시작"

# 1. 웹 인터페이스 체크
check_process "streamlit run web_interface.py" \
    "logs/web.pid" \
    "nohup streamlit run web_interface.py > logs/web_interface.log 2>&1 &"

# 2. 자동 인덱싱 체크
check_process "auto_indexer.py" \
    "logs/indexer.pid" \
    "nohup python3 auto_indexer.py > logs/auto_indexer.log 2>&1 &"

# 3. OCR 모니터 체크
check_process "auto_ocr_monitor.py" \
    "logs/ocr.pid" \
    "nohup python3 auto_ocr_monitor.py > logs/ocr_monitor.log 2>&1 &"

# 4. 시스템 리소스 체크
check_memory
check_disk

log "✅ 시스템 감시 완료"