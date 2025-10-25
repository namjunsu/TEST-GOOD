#!/bin/bash
# =============================================
# AI-CHAT 운영 점검 커맨드
# 운영 환경 상태 확인 및 진단
# =============================================

set -euo pipefail

# ==================== 설정 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

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

    case "$level" in
        INFO) echo -e "${CYAN}ℹ️  $message${NC}" ;;
        WARN) echo -e "${YELLOW}⚠️  $message${NC}" ;;
        ERROR) echo -e "${RED}❌ $message${NC}" ;;
        SUCCESS) echo -e "${GREEN}✅ $message${NC}" ;;
    esac
}

section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# 1. 의존성 확인
check_dependencies() {
    section "📦 의존성 확인"

    log INFO "Python 가상환경 확인..."
    if [ -d "${PROJECT_ROOT}/.venv" ]; then
        log SUCCESS "가상환경 존재: .venv"

        # 가상환경 활성화
        source "${PROJECT_ROOT}/.venv/bin/activate"

        # 패키지 개수 확인
        local pkg_count=$(pip list 2>/dev/null | wc -l)
        log INFO "설치된 패키지: ${pkg_count}개"

        # requirements.txt와 비교
        if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
            local required_count=$(grep -c '^[a-zA-Z]' "${PROJECT_ROOT}/requirements.txt" || echo 0)
            log INFO "필수 패키지: ${required_count}개"
        fi

        # requirements.lock.txt 확인
        if [ -f "${PROJECT_ROOT}/requirements.lock.txt" ]; then
            log SUCCESS "잠금 파일 존재: requirements.lock.txt"
        else
            log WARN "잠금 파일 없음 (pip freeze > requirements.lock.txt 권장)"
        fi
    else
        log ERROR "가상환경 없음: .venv"
        return 1
    fi
}

# 2. 로그 확인
check_logs() {
    section "📝 로그 확인"

    local log_file="${PROJECT_ROOT}/var/log/app.log"

    if [ -f "$log_file" ]; then
        log SUCCESS "로그 파일 존재: $log_file"

        local log_size=$(du -h "$log_file" | cut -f1)
        local log_lines=$(wc -l < "$log_file")

        log INFO "로그 크기: $log_size"
        log INFO "로그 라인: ${log_lines}줄"

        # 최근 에러 확인
        local error_count=$(grep -c "ERROR" "$log_file" 2>/dev/null || echo 0)
        local warning_count=$(grep -c "WARNING" "$log_file" 2>/dev/null || echo 0)

        if [ "$error_count" -gt 0 ]; then
            log WARN "에러 로그: ${error_count}건"
            echo ""
            echo "최근 에러 (최대 5건):"
            grep "ERROR" "$log_file" | tail -5
        else
            log SUCCESS "에러 로그: 0건"
        fi

        if [ "$warning_count" -gt 0 ]; then
            log INFO "경고 로그: ${warning_count}건"
        fi

        # 로그 회전 확인
        local rotated_count=$(ls -1 "${PROJECT_ROOT}/var/log/app.log"* 2>/dev/null | wc -l)
        log INFO "로그 회전 파일: ${rotated_count}개"

    else
        log ERROR "로그 파일 없음: $log_file"
        return 1
    fi
}

# 3. DB/WAL 확인
check_database() {
    section "🗄️  데이터베이스 확인"

    local db_dir="${PROJECT_ROOT}/var/db"

    if [ ! -d "$db_dir" ]; then
        log ERROR "DB 디렉토리 없음: $db_dir"
        return 1
    fi

    # DB 파일 목록
    log INFO "DB 파일 목록:"
    for db_file in "$db_dir"/*.db; do
        if [ -f "$db_file" ]; then
            local db_name=$(basename "$db_file")
            local db_size=$(du -h "$db_file" | cut -f1)

            echo "  📄 $db_name (크기: $db_size)"

            # WAL 모드 확인
            if command -v sqlite3 >/dev/null 2>&1; then
                local journal_mode=$(sqlite3 "$db_file" 'PRAGMA journal_mode;' 2>/dev/null || echo "N/A")
                if [ "$journal_mode" = "wal" ]; then
                    log SUCCESS "    WAL 모드: ON"
                else
                    log WARN "    WAL 모드: $journal_mode (WAL 아님)"
                fi

                # busy_timeout 확인
                local busy_timeout=$(sqlite3 "$db_file" 'PRAGMA busy_timeout;' 2>/dev/null || echo "N/A")
                log INFO "    busy_timeout: ${busy_timeout}ms"

                # 테이블 수 확인
                local table_count=$(sqlite3 "$db_file" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "N/A")
                log INFO "    테이블 수: ${table_count}개"
            fi

            # WAL 파일 존재 확인
            if [ -f "${db_file}-wal" ]; then
                local wal_size=$(du -h "${db_file}-wal" | cut -f1)
                log INFO "    WAL 파일: $wal_size"
            fi
        fi
    done
}

# 4. 벤치마크 확인
check_benchmark() {
    section "📊 벤치마크 결과"

    local bench_file="${PROJECT_ROOT}/var/bench_results.csv"

    if [ -f "$bench_file" ]; then
        log SUCCESS "벤치마크 결과 존재: $bench_file"

        echo ""
        echo "최근 벤치마크 결과 (최대 5건):"
        if command -v column >/dev/null 2>&1; then
            tail -6 "$bench_file" | column -s, -t
        else
            tail -6 "$bench_file"
        fi
    else
        log WARN "벤치마크 결과 없음"
        log INFO "실행: python scripts/bench_rag.py"
    fi
}

# 5. 프로세스 확인
check_process() {
    section "🔄 프로세스 확인"

    log INFO "Streamlit 프로세스 확인..."

    local streamlit_pids=$(pgrep -f "streamlit.*web_interface" 2>/dev/null || echo "")

    if [ -n "$streamlit_pids" ]; then
        log SUCCESS "Streamlit 실행 중 (PID: $streamlit_pids)"

        # 포트 확인
        if command -v lsof >/dev/null 2>&1; then
            local ports=$(lsof -i -P -n 2>/dev/null | grep -E "streamlit.*LISTEN" | awk '{print $9}' | cut -d':' -f2 || echo "")
            if [ -n "$ports" ]; then
                log INFO "리스닝 포트: $ports"
            fi
        fi

        # 메모리 사용량
        local mem_usage=$(ps -o rss= -p "$streamlit_pids" | awk '{sum+=$1} END {print sum/1024}' 2>/dev/null || echo "N/A")
        log INFO "메모리 사용: ${mem_usage}MB"

    else
        log WARN "Streamlit 실행 중 아님"
        log INFO "시작: ./start_ai_chat.sh"
    fi
}

# 6. 디스크 사용량
check_disk() {
    section "💾 디스크 사용량"

    log INFO "프로젝트 디렉토리별 크기:"

    # 주요 디렉토리 크기
    for dir in var docs rag_system modules models .venv; do
        if [ -d "${PROJECT_ROOT}/$dir" ]; then
            local size=$(du -sh "${PROJECT_ROOT}/$dir" 2>/dev/null | cut -f1)
            echo "  📁 $dir: $size"
        fi
    done

    # 전체 프로젝트 크기
    echo ""
    local total_size=$(du -sh "$PROJECT_ROOT" 2>/dev/null | cut -f1)
    log INFO "전체 프로젝트 크기: $total_size"
}

# 7. 백업 상태
check_backup() {
    section "💼 백업 상태"

    local backup_dir="${PROJECT_ROOT}/var/backups"

    if [ -d "$backup_dir" ] && [ -n "$(ls -A "$backup_dir" 2>/dev/null)" ]; then
        local backup_count=$(find "$backup_dir" -mindepth 1 -maxdepth 1 -type d | wc -l)
        log SUCCESS "백업 존재: ${backup_count}개"

        # 최신 백업
        local latest_backup=$(ls -1t "$backup_dir" | head -1)
        if [ -n "$latest_backup" ]; then
            local backup_size=$(du -sh "${backup_dir}/${latest_backup}" | cut -f1)
            log INFO "최신 백업: $latest_backup (크기: $backup_size)"
        fi

        # 가장 오래된 백업
        local oldest_backup=$(ls -1t "$backup_dir" | tail -1)
        if [ -n "$oldest_backup" ]; then
            log INFO "가장 오래된 백업: $oldest_backup"
        fi
    else
        log WARN "백업 없음"
        log INFO "실행: ./scripts/backup_db.sh"
    fi
}

# 8. 상태 보고서 생성
generate_report() {
    section "📋 상태 보고서 생성"

    local report_file="${PROJECT_ROOT}/var/ops_report_$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "[운영체크] $(date '+%Y-%m-%d %H:%M:%S KST')"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""

        # Warmup 상태
        if pgrep -f "streamlit.*web_interface" >/dev/null 2>&1; then
            echo "- Warmup: OK (Streamlit 실행 중)"
        else
            echo "- Warmup: NG (Streamlit 미실행)"
        fi

        # WAL 모드
        local wal_status="N/A"
        if [ -f "${PROJECT_ROOT}/var/db/metadata.db" ] && command -v sqlite3 >/dev/null 2>&1; then
            wal_status=$(sqlite3 "${PROJECT_ROOT}/var/db/metadata.db" 'PRAGMA journal_mode;' 2>/dev/null || echo "N/A")
        fi
        echo "- WAL: ${wal_status} / busy_timeout=5000ms"

        # 성능 (최신 벤치마크에서 추출)
        if [ -f "${PROJECT_ROOT}/var/bench_results.csv" ]; then
            local latest_bench=$(tail -1 "${PROJECT_ROOT}/var/bench_results.csv")
            echo "- 성능: (벤치마크 참조)"
            echo "  $latest_bench"
        else
            echo "- 성능: N/A (벤치마크 미실행)"
        fi

        # 에러 코드
        local error_count=0
        if [ -f "${PROJECT_ROOT}/var/log/app.log" ]; then
            error_count=$(grep -c "E_" "${PROJECT_ROOT}/var/log/app.log" 2>/dev/null || echo 0)
        fi
        echo "- 에러코드 발생: ${error_count}건"

        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    } > "$report_file"

    log SUCCESS "상태 보고서 생성: $report_file"
    cat "$report_file"
}

# ==================== 메인 로직 ====================

main() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 AI-CHAT 운영 점검"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 모든 검사 실행
    check_dependencies
    check_logs
    check_database
    check_benchmark
    check_process
    check_disk
    check_backup

    # 상태 보고서 생성
    generate_report

    echo ""
    log SUCCESS "✅ 운영 점검 완료"
}

# ==================== 실행 ====================

main "$@"
