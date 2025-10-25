#!/bin/bash
# =============================================
# AI-CHAT DB 복구 스크립트
# =============================================

set -euo pipefail

# ==================== 설정 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
BACKUP_DIR="${PROJECT_ROOT}/var/backups"
DB_DIR="${PROJECT_ROOT}/var/db"

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

# ==================== 함수 ====================

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        INFO) echo -e "${GREEN}[${timestamp}] ℹ️  $message${NC}" ;;
        WARN) echo -e "${YELLOW}[${timestamp}] ⚠️  $message${NC}" ;;
        ERROR) echo -e "${RED}[${timestamp}] ❌ $message${NC}" ;;
        SUCCESS) echo -e "${GREEN}[${timestamp}] ✅ $message${NC}" ;;
    esac
}

# 백업 목록 출력
list_backups() {
    log INFO "사용 가능한 백업:"
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        log ERROR "백업이 없습니다"
        exit 1
    fi

    local index=1
    while IFS= read -r -d '' backup_dir; do
        local dir_name=$(basename "$backup_dir")
        local size=$(du -sh "$backup_dir" | cut -f1)
        local file_count=$(find "$backup_dir" -type f -name "*.db.gz" | wc -l)

        echo "  $index) $dir_name (크기: $size, DB 파일: ${file_count}개)"
        ((index++))
    done < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -zr || true)

    echo ""
}

# 백업 선택
select_backup() {
    list_backups

    read -p "복구할 백업 번호 입력 (0=취소): " selection

    if [ "$selection" = "0" ]; then
        log INFO "사용자가 취소했습니다"
        exit 0
    fi

    local index=1
    while IFS= read -r -d '' backup_dir; do
        if [ "$index" -eq "$selection" ]; then
            echo "$backup_dir"
            return 0
        fi
        ((index++))
    done < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -zr || true)

    log ERROR "잘못된 선택: $selection"
    exit 1
}

# DB 복구
restore_db() {
    local backup_path="$1"

    log INFO "=" * 70
    log INFO "🔄 DB 복구 시작"
    log INFO "백업: $backup_path"
    log INFO "=" * 70

    # 확인
    echo ""
    log WARN "⚠️  경고: 현재 DB 파일을 덮어씁니다!"
    read -p "계속하시겠습니까? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        log INFO "사용자가 취소했습니다"
        exit 0
    fi

    # 현재 DB 백업 (안전장치)
    local safety_backup="${DB_DIR}/pre_restore_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$safety_backup"
    log INFO "안전 백업 생성: $safety_backup"
    cp -r "$DB_DIR"/*.db "$safety_backup/" 2>/dev/null || true

    # 복구
    local restored=0
    for gz_file in "$backup_path"/*.db.gz; do
        if [ -f "$gz_file" ]; then
            local db_name=$(basename "$gz_file" .gz)
            local target_file="${DB_DIR}/${db_name}"

            log INFO "복구 중: $db_name"

            # 압축 해제
            gunzip -c "$gz_file" > "$target_file"

            # WAL/SHM 파일도 복구 (있으면)
            if [ -f "${gz_file%.db.gz}-wal.gz" ]; then
                gunzip -c "${gz_file%.db.gz}-wal.gz" > "${target_file}-wal"
            fi
            if [ -f "${gz_file%.db.gz}-shm.gz" ]; then
                gunzip -c "${gz_file%.db.gz}-shm.gz" > "${target_file}-shm"
            fi

            # 검증
            if sqlite3 "$target_file" "PRAGMA integrity_check;" >/dev/null 2>&1; then
                log SUCCESS "복구 완료: $db_name"
                ((restored++))
            else
                log ERROR "복구 실패 (무결성 검사 실패): $db_name"
            fi
        fi
    done

    log SUCCESS "=" * 70
    log SUCCESS "✅ DB 복구 완료: ${restored}개 파일"
    log SUCCESS "안전 백업: $safety_backup"
    log SUCCESS "=" * 70
}

# ==================== 메인 로직 ====================

main() {
    log INFO "AI-CHAT DB 복구 도구"

    # 백업 선택
    local backup_path=$(select_backup)

    # 복구 실행
    restore_db "$backup_path"
}

# ==================== 실행 ====================

main "$@"
