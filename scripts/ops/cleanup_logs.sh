#!/bin/bash
# =============================================
# AI-CHAT 로그 자동 정리 스크립트
# 일 1회 실행 권장 (cron: 0 3 * * *)
# =============================================

set -euo pipefail

# ==================== 설정 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../.."
LOG_DIR="${PROJECT_ROOT}/logs"
ARCHIVE_DIR="${PROJECT_ROOT}/var/log_archives"

# 보관 기간 설정
RETENTION_DAYS=${LOG_RETENTION_DAYS:-30}      # 로그 파일 보관 기간
ARCHIVE_RETENTION_DAYS=${ARCHIVE_RETENTION_DAYS:-90}  # 압축 아카이브 보관 기간

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# ==================== 함수 ====================

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        INFO)
            echo -e "${CYAN}[${timestamp}] INFO: $message${NC}"
            ;;
        WARN)
            echo -e "${YELLOW}[${timestamp}] WARN: $message${NC}"
            ;;
        ERROR)
            echo -e "${RED}[${timestamp}] ERROR: $message${NC}"
            ;;
        SUCCESS)
            echo -e "${GREEN}[${timestamp}] OK: $message${NC}"
            ;;
    esac
}

# 디스크 사용량 확인
check_disk_usage() {
    local dir="$1"
    if [ -d "$dir" ]; then
        du -sh "$dir" 2>/dev/null | cut -f1
    else
        echo "0"
    fi
}

# 오래된 로그 파일 아카이브
archive_old_logs() {
    log INFO "오래된 로그 파일 아카이브 중 (${RETENTION_DAYS}일 이상)"

    # 아카이브 디렉토리 생성
    mkdir -p "$ARCHIVE_DIR"

    local archive_date=$(date '+%Y%m%d')
    local archive_file="${ARCHIVE_DIR}/logs_${archive_date}.tar.gz"
    local archived_count=0
    local temp_list=$(mktemp)

    # 오래된 로그 파일 찾기
    find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.json" -o -name "*.jsonl" \) \
        -mtime +${RETENTION_DAYS} 2>/dev/null > "$temp_list" || true

    if [ -s "$temp_list" ]; then
        archived_count=$(wc -l < "$temp_list")

        # 아카이브 생성
        if tar -czf "$archive_file" -T "$temp_list" 2>/dev/null; then
            # 원본 파일 삭제
            while IFS= read -r file; do
                rm -f "$file"
            done < "$temp_list"

            local archive_size=$(du -h "$archive_file" | cut -f1)
            log SUCCESS "아카이브 완료: ${archived_count}개 파일 -> ${archive_file} (${archive_size})"
        else
            log WARN "아카이브 생성 실패, 개별 삭제 진행"
            while IFS= read -r file; do
                rm -f "$file"
            done < "$temp_list"
            log SUCCESS "${archived_count}개 파일 삭제 완료"
        fi
    else
        log INFO "아카이브할 파일 없음"
    fi

    rm -f "$temp_list"
}

# 오래된 아카이브 삭제
cleanup_old_archives() {
    log INFO "오래된 아카이브 정리 중 (${ARCHIVE_RETENTION_DAYS}일 이상)"

    if [ ! -d "$ARCHIVE_DIR" ]; then
        log INFO "아카이브 디렉토리 없음"
        return 0
    fi

    local deleted_count=0

    while IFS= read -r -d '' archive; do
        rm -f "$archive"
        ((deleted_count++))
    done < <(find "$ARCHIVE_DIR" -type f -name "logs_*.tar.gz" -mtime +${ARCHIVE_RETENTION_DAYS} -print0 2>/dev/null || true)

    if [ "$deleted_count" -gt 0 ]; then
        log SUCCESS "오래된 아카이브 ${deleted_count}개 삭제"
    else
        log INFO "삭제할 아카이브 없음"
    fi
}

# 빈 로그 파일 정리
cleanup_empty_logs() {
    log INFO "빈 로그 파일 정리 중"

    local deleted_count=0

    while IFS= read -r -d '' file; do
        rm -f "$file"
        ((deleted_count++))
    done < <(find "$LOG_DIR" -type f -empty -print0 2>/dev/null || true)

    if [ "$deleted_count" -gt 0 ]; then
        log SUCCESS "빈 파일 ${deleted_count}개 삭제"
    else
        log INFO "빈 파일 없음"
    fi
}

# 로테이션된 로그 정리 (*.log.1, *.log.2 등)
cleanup_rotated_logs() {
    log INFO "로테이션된 로그 파일 정리 중"

    local deleted_count=0

    # .log.N 형태의 로테이션 파일 중 7일 이상된 것 삭제
    while IFS= read -r -d '' file; do
        rm -f "$file"
        ((deleted_count++))
    done < <(find "$LOG_DIR" -type f -regex '.*\.log\.[0-9]+' -mtime +7 -print0 2>/dev/null || true)

    if [ "$deleted_count" -gt 0 ]; then
        log SUCCESS "로테이션 파일 ${deleted_count}개 삭제"
    else
        log INFO "삭제할 로테이션 파일 없음"
    fi
}

# 통계 출력
print_stats() {
    log INFO "=========================================="
    log INFO "현재 로그 디렉토리 상태"
    log INFO "=========================================="

    local log_size=$(check_disk_usage "$LOG_DIR")
    local archive_size=$(check_disk_usage "$ARCHIVE_DIR")
    local file_count=$(find "$LOG_DIR" -type f 2>/dev/null | wc -l)
    local archive_count=$(find "$ARCHIVE_DIR" -type f -name "*.tar.gz" 2>/dev/null | wc -l)

    echo ""
    echo "  로그 디렉토리: $LOG_DIR"
    echo "  - 용량: $log_size"
    echo "  - 파일 수: ${file_count}개"
    echo ""
    echo "  아카이브 디렉토리: $ARCHIVE_DIR"
    echo "  - 용량: $archive_size"
    echo "  - 아카이브 수: ${archive_count}개"
    echo ""
    echo "  설정:"
    echo "  - 로그 보관 기간: ${RETENTION_DAYS}일"
    echo "  - 아카이브 보관 기간: ${ARCHIVE_RETENTION_DAYS}일"
    echo ""
}

# ==================== 메인 ====================

main() {
    log INFO "=========================================="
    log INFO "AI-CHAT 로그 정리 시작"
    log INFO "=========================================="

    # 로그 디렉토리 확인
    if [ ! -d "$LOG_DIR" ]; then
        log WARN "로그 디렉토리 없음: $LOG_DIR"
        exit 0
    fi

    local before_size=$(check_disk_usage "$LOG_DIR")

    # 1. 빈 파일 정리
    cleanup_empty_logs

    # 2. 로테이션 파일 정리
    cleanup_rotated_logs

    # 3. 오래된 로그 아카이브
    archive_old_logs

    # 4. 오래된 아카이브 삭제
    cleanup_old_archives

    local after_size=$(check_disk_usage "$LOG_DIR")

    # 5. 통계 출력
    print_stats

    log SUCCESS "=========================================="
    log SUCCESS "로그 정리 완료"
    log SUCCESS "정리 전: $before_size -> 정리 후: $after_size"
    log SUCCESS "=========================================="
}

# 실행
main "$@"
