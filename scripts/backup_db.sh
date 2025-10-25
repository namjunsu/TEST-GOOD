#!/bin/bash
# =============================================
# AI-CHAT DB 백업 스크립트
# 일 1회 실행 권장 (cron: 0 2 * * *)
# =============================================

set -euo pipefail

# ==================== 설정 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
BACKUP_DIR="${PROJECT_ROOT}/var/backups"
DB_DIR="${PROJECT_ROOT}/var/db"
RETENTION_DAYS=7

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
        INFO)
            echo -e "${GREEN}[${timestamp}] ℹ️  $message${NC}"
            ;;
        WARN)
            echo -e "${YELLOW}[${timestamp}] ⚠️  $message${NC}"
            ;;
        ERROR)
            echo -e "${RED}[${timestamp}] ❌ $message${NC}"
            ;;
        SUCCESS)
            echo -e "${GREEN}[${timestamp}] ✅ $message${NC}"
            ;;
    esac
}

# 백업 디렉토리 생성
create_backup_dir() {
    local backup_date=$(date '+%Y%m%d_%H%M%S')
    local backup_path="${BACKUP_DIR}/${backup_date}"

    if [ ! -d "$backup_path" ]; then
        mkdir -p "$backup_path"
        log SUCCESS "백업 디렉토리 생성: $backup_path"
    fi

    echo "$backup_path"
}

# DB 파일 백업
backup_db_file() {
    local db_file="$1"
    local backup_path="$2"

    if [ ! -f "$db_file" ]; then
        log WARN "DB 파일 없음: $db_file (건너뜀)"
        return 0
    fi

    local db_name=$(basename "$db_file")
    local backup_file="${backup_path}/${db_name}"

    # SQLite DB인 경우 .backup 명령 사용 (안전한 핫 백업)
    if command -v sqlite3 >/dev/null 2>&1; then
        log INFO "백업 중: $db_name (sqlite3 .backup)"
        sqlite3 "$db_file" ".backup '$backup_file'"
    else
        # sqlite3 없으면 단순 복사 (권장하지 않음)
        log WARN "sqlite3 명령 없음, 파일 복사 사용"
        cp "$db_file" "$backup_file"
    fi

    # WAL/SHM 파일도 백업
    if [ -f "${db_file}-wal" ]; then
        cp "${db_file}-wal" "${backup_file}-wal"
    fi
    if [ -f "${db_file}-shm" ]; then
        cp "${db_file}-shm" "${backup_file}-shm"
    fi

    # 백업 파일 압축
    log INFO "압축 중: $db_name"
    gzip -f "$backup_file"

    # 압축 파일 크기 확인
    local compressed_size=$(du -h "${backup_file}.gz" | cut -f1)
    log SUCCESS "백업 완료: $db_name (크기: $compressed_size)"

    return 0
}

# 오래된 백업 삭제
cleanup_old_backups() {
    log INFO "오래된 백업 정리 중 (${RETENTION_DAYS}일 이상)"

    local deleted_count=0
    while IFS= read -r -d '' backup_dir; do
        local dir_name=$(basename "$backup_dir")
        # 디렉토리명에서 날짜 추출 (YYYYMMDD_HHMMSS)
        local backup_date=$(echo "$dir_name" | cut -d'_' -f1)

        if [ -n "$backup_date" ]; then
            local backup_timestamp=$(date -d "$backup_date" +%s 2>/dev/null || echo 0)
            local cutoff_timestamp=$(date -d "$RETENTION_DAYS days ago" +%s)

            if [ "$backup_timestamp" -lt "$cutoff_timestamp" ]; then
                log INFO "삭제: $dir_name"
                rm -rf "$backup_dir"
                ((deleted_count++))
            fi
        fi
    done < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null || true)

    if [ "$deleted_count" -gt 0 ]; then
        log SUCCESS "오래된 백업 ${deleted_count}개 삭제 완료"
    else
        log INFO "삭제할 백업 없음"
    fi
}

# 백업 검증
verify_backup() {
    local backup_path="$1"

    log INFO "백업 파일 검증 중..."

    local verified=0
    local failed=0

    for gz_file in "$backup_path"/*.db.gz; do
        if [ -f "$gz_file" ]; then
            # 압축 파일 무결성 확인
            if gzip -t "$gz_file" 2>/dev/null; then
                ((verified++))
            else
                log ERROR "압축 파일 손상: $gz_file"
                ((failed++))
            fi
        fi
    done

    if [ "$failed" -eq 0 ]; then
        log SUCCESS "백업 검증 완료: ${verified}개 파일 정상"
        return 0
    else
        log ERROR "백업 검증 실패: ${failed}개 파일 손상"
        return 1
    fi
}

# 백업 목록 출력
list_backups() {
    log INFO "현재 백업 목록:"
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        echo "  (백업 없음)"
        return 0
    fi

    local backup_count=0
    while IFS= read -r -d '' backup_dir; do
        local dir_name=$(basename "$backup_dir")
        local size=$(du -sh "$backup_dir" | cut -f1)
        local file_count=$(find "$backup_dir" -type f | wc -l)

        echo "  📦 $dir_name (크기: $size, 파일: ${file_count}개)"
        ((backup_count++))
    done < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -zr || true)

    echo ""
    log INFO "총 ${backup_count}개 백업"
}

# ==================== 메인 로직 ====================

main() {
    log INFO "=" * 70
    log INFO "🔄 AI-CHAT DB 백업 시작"
    log INFO "=" * 70

    # 1. 백업 디렉토리 생성
    local backup_path=$(create_backup_dir)

    # 2. DB 파일 백업
    log INFO "DB 파일 백업 중..."

    # metadata.db
    if [ -f "${DB_DIR}/metadata.db" ]; then
        backup_db_file "${DB_DIR}/metadata.db" "$backup_path"
    fi

    # everything_index.db
    if [ -f "${DB_DIR}/everything_index.db" ]; then
        backup_db_file "${DB_DIR}/everything_index.db" "$backup_path"
    fi

    # 기타 .db 파일 백업
    for db_file in "${DB_DIR}"/*.db; do
        if [ -f "$db_file" ]; then
            local db_name=$(basename "$db_file")
            if [ "$db_name" != "metadata.db" ] && [ "$db_name" != "everything_index.db" ]; then
                backup_db_file "$db_file" "$backup_path"
            fi
        fi
    done

    # 3. 백업 검증
    verify_backup "$backup_path"

    # 4. 오래된 백업 정리
    cleanup_old_backups

    # 5. 백업 목록 출력
    list_backups

    log SUCCESS "=" * 70
    log SUCCESS "✅ DB 백업 완료"
    log SUCCESS "백업 경로: $backup_path"
    log SUCCESS "=" * 70
}

# ==================== 실행 ====================

main "$@"
