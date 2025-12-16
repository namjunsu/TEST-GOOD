#!/bin/bash
# =============================================
# AI-CHAT Cron 자동화 설정 스크립트
# 백업, 로그 정리, 헬스체크 스케줄 등록
# =============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

log() {
    local level="$1"
    shift
    case "$level" in
        INFO)  echo -e "${CYAN}[INFO]${NC} $*" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} $*" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} $*" ;;
        OK)    echo -e "${GREEN}[OK]${NC} $*" ;;
    esac
}

# 현재 crontab 확인
show_current() {
    log INFO "현재 등록된 cron 작업:"
    echo ""
    crontab -l 2>/dev/null | grep -E "(AI-CHAT|backup_db|cleanup_logs|healthcheck)" || echo "  (AI-CHAT 관련 작업 없음)"
    echo ""
}

# cron 작업 추가
add_cron_jobs() {
    log INFO "AI-CHAT cron 작업 등록 중..."

    # 기존 crontab 백업
    local temp_cron=$(mktemp)
    crontab -l 2>/dev/null > "$temp_cron" || true

    # 기존 AI-CHAT 관련 작업 제거 (중복 방지)
    grep -v "AI-CHAT" "$temp_cron" > "${temp_cron}.clean" 2>/dev/null || true
    mv "${temp_cron}.clean" "$temp_cron"

    # 새 작업 추가
    cat >> "$temp_cron" << EOF

# ============================================================================
# AI-CHAT 자동화 작업 (setup_cron.sh로 생성됨)
# ============================================================================

# DB 백업 - 매일 새벽 2시
0 2 * * * ${PROJECT_ROOT}/scripts/backup_db.sh >> ${PROJECT_ROOT}/logs/cron_backup.log 2>&1

# 로그 정리 - 매일 새벽 3시
0 3 * * * ${PROJECT_ROOT}/scripts/ops/cleanup_logs.sh >> ${PROJECT_ROOT}/logs/cron_cleanup.log 2>&1

# 헬스체크 - 매 6시간마다 (0시, 6시, 12시, 18시)
0 */6 * * * cd ${PROJECT_ROOT} && ${PROJECT_ROOT}/.venv/bin/python ${PROJECT_ROOT}/scripts/ops/healthcheck.py >> ${PROJECT_ROOT}/logs/cron_healthcheck.log 2>&1

EOF

    # crontab 등록
    crontab "$temp_cron"
    rm -f "$temp_cron"

    log OK "cron 작업 등록 완료!"
}

# cron 작업 제거
remove_cron_jobs() {
    log INFO "AI-CHAT cron 작업 제거 중..."

    local temp_cron=$(mktemp)
    crontab -l 2>/dev/null | grep -v "AI-CHAT" | grep -v "backup_db.sh" | grep -v "cleanup_logs.sh" | grep -v "healthcheck.py" > "$temp_cron" || true

    if [ -s "$temp_cron" ]; then
        crontab "$temp_cron"
    else
        crontab -r 2>/dev/null || true
    fi
    rm -f "$temp_cron"

    log OK "cron 작업 제거 완료!"
}

# 도움말
usage() {
    echo ""
    echo "AI-CHAT Cron 설정 스크립트"
    echo ""
    echo "사용법: $0 [명령]"
    echo ""
    echo "명령:"
    echo "  install   - cron 작업 등록 (백업, 로그 정리, 헬스체크)"
    echo "  remove    - cron 작업 제거"
    echo "  status    - 현재 상태 확인"
    echo "  help      - 도움말"
    echo ""
    echo "등록되는 작업:"
    echo "  - DB 백업: 매일 02:00"
    echo "  - 로그 정리: 매일 03:00"
    echo "  - 헬스체크: 매 6시간 (00:00, 06:00, 12:00, 18:00)"
    echo ""
}

# 메인
main() {
    local cmd="${1:-help}"

    case "$cmd" in
        install|add)
            show_current
            add_cron_jobs
            echo ""
            show_current
            ;;
        remove|delete)
            remove_cron_jobs
            show_current
            ;;
        status|show)
            show_current
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log ERROR "알 수 없는 명령: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
