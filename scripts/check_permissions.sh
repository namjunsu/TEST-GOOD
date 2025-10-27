#!/bin/bash
# =============================================
# AI-CHAT 권한/경로 검사 스크립트
# =============================================

set -euo pipefail

# ==================== 설정 ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

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

    case "$level" in
        INFO) echo -e "${GREEN}ℹ️  $message${NC}" ;;
        WARN) echo -e "${YELLOW}⚠️  $message${NC}" ;;
        ERROR) echo -e "${RED}❌ $message${NC}" ;;
        SUCCESS) echo -e "${GREEN}✅ $message${NC}" ;;
    esac
}

check_dir_writable() {
    local dir_path="$1"
    local dir_name="$2"

    if [ ! -d "$dir_path" ]; then
        log WARN "$dir_name 디렉토리 없음: $dir_path (생성 시도)"
        if mkdir -p "$dir_path" 2>/dev/null; then
            log SUCCESS "$dir_name 디렉토리 생성 완료"
        else
            log ERROR "$dir_name 디렉토리 생성 실패"
            return 1
        fi
    fi

    if [ -w "$dir_path" ]; then
        log SUCCESS "$dir_name 쓰기 권한 OK"
        return 0
    else
        log ERROR "$dir_name 쓰기 권한 없음: $dir_path"
        return 1
    fi
}

check_file_readable() {
    local file_path="$1"
    local file_name="$2"

    if [ ! -f "$file_path" ]; then
        log WARN "$file_name 파일 없음: $file_path"
        return 1
    fi

    if [ -r "$file_path" ]; then
        log SUCCESS "$file_name 읽기 권한 OK"
        return 0
    else
        log ERROR "$file_name 읽기 권한 없음: $file_path"
        return 1
    fi
}

check_external_db_paths() {
    log INFO "외부 경로 DB 생성 검사 중..."

    # 프로젝트 루트 외부에서 DB 파일 검색
    local external_dbs=$(find / -name "*.db" -path "*AI-CHAT*" ! -path "${PROJECT_ROOT}/*" 2>/dev/null || true)

    if [ -n "$external_dbs" ]; then
        log WARN "외부 경로에 DB 파일 발견:"
        echo "$external_dbs" | while read -r db_file; do
            echo "  - $db_file"
        done
        log WARN "프로젝트 루트로 DB 파일 이동 권장"
        return 1
    else
        log SUCCESS "외부 경로 DB 파일 없음"
        return 0
    fi
}

# ==================== 메인 로직 ====================

main() {
    log INFO "=" * 70
    log INFO "🔍 AI-CHAT 권한/경로 검사"
    log INFO "=" * 70

    local passed=0
    local failed=0

    echo ""
    log INFO "1. 필수 디렉토리 쓰기 권한 확인"
    echo ""

    # var/* 디렉토리 검사
    check_dir_writable "${PROJECT_ROOT}/var" "var" && ((passed++)) || ((failed++))
    check_dir_writable "${PROJECT_ROOT}/var/log" "var/log" && ((passed++)) || ((failed++))
    check_dir_writable "${PROJECT_ROOT}/var/db" "var/db" && ((passed++)) || ((failed++))
    check_dir_writable "${PROJECT_ROOT}/var/backups" "var/backups" && ((passed++)) || ((failed++))

    echo ""
    log INFO "2. 필수 파일 읽기 권한 확인"
    echo ""

    # 설정 파일 검사
    check_file_readable "${PROJECT_ROOT}/config.py" "config.py" && ((passed++)) || ((failed++))
    check_file_readable "${PROJECT_ROOT}/requirements.txt" "requirements.txt" && ((passed++)) || ((failed++))

    # 실행 파일 검사
    check_file_readable "${PROJECT_ROOT}/web_interface.py" "web_interface.py" && ((passed++)) || ((failed++))

    echo ""
    log INFO "3. 외부 경로 DB 파일 검사"
    echo ""

    # 외부 경로 DB 검사 (느릴 수 있으므로 타임아웃 설정)
    timeout 10 bash -c "$(declare -f check_external_db_paths); check_external_db_paths" && ((passed++)) || {
        log WARN "외부 경로 검사 타임아웃 또는 실패"
        ((failed++))
    }

    echo ""
    log INFO "4. 실행 사용자 정보"
    echo ""

    log INFO "실행 사용자: $(whoami)"
    log INFO "사용자 ID: $(id -u)"
    log INFO "그룹 ID: $(id -g)"
    log INFO "홈 디렉토리: $HOME"

    echo ""
    log INFO "=" * 70
    log INFO "📊 검사 결과"
    log INFO "=" * 70
    log INFO "통과: ${passed}개"
    log INFO "실패: ${failed}개"

    if [ "$failed" -eq 0 ]; then
        log SUCCESS "✅ 모든 검사 통과"
        exit 0
    else
        log ERROR "❌ ${failed}개 항목 실패"
        log ERROR "권한/경로 문제 해결 후 재실행하세요"
        exit 1
    fi
}

# ==================== 실행 ====================

main "$@"
