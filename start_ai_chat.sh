#!/bin/bash
# =============================================
# AI-CHAT 간편 실행 스크립트 (개선 버전)
# Author: System
# Version: 2.0
# Date: 2025-10-24
# =============================================

set -euo pipefail  # 에러 발생 시 즉시 종료, 미정의 변수 사용 금지

# ==================== 설정 ====================

# 동적 경로 감지 (스크립트 위치 기반)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# 설정 파일 로드 (있으면)
CONFIG_FILE="${PROJECT_ROOT}/.env"
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# 환경 변수 또는 기본값
PORT="${AI_CHAT_PORT:-8501}"
HOST="${AI_CHAT_HOST:-0.0.0.0}"
VENV_NAME="${AI_CHAT_VENV:-.venv}"
LOG_FILE="${PROJECT_ROOT}/logs/start_$(date +%Y%m%d_%H%M%S).log"

# 색상 정의
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly CYAN='\033[0;36m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# ==================== 함수 정의 ====================

# 로그 함수
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # 로그 파일에 기록
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"

    # 화면 출력
    case "$level" in
        INFO)
            echo -e "${GREEN}ℹ️  $message${NC}"
            ;;
        WARN)
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        ERROR)
            echo -e "${RED}❌ $message${NC}"
            ;;
        SUCCESS)
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        *)
            echo "$message"
            ;;
    esac
}

# 에러 핸들러
error_handler() {
    local line_num="$1"
    log ERROR "스크립트 오류 발생 (라인 $line_num)"
    log ERROR "로그 확인: $LOG_FILE"
    cleanup
    exit 1
}

# Ctrl+C 핸들러
interrupt_handler() {
    echo ""
    log WARN "사용자가 중단했습니다"
    cleanup
    exit 130
}

# 클린업 함수
cleanup() {
    log INFO "정리 작업 중..."
    # FastAPI 서버 종료
    if [ -n "${API_PID:-}" ]; then
        log INFO "FastAPI 서버 종료 (PID: $API_PID)..."
        kill "$API_PID" 2>/dev/null || true
    fi
    # uvicorn 프로세스 정리
    pkill -f "uvicorn.*app.api.main" 2>/dev/null || true
}

# 프로세스 체크 (더 정확한 버전)
check_running_process() {
    local port="$1"

    # 포트로 프로세스 찾기 (더 정확함)
    if command -v lsof >/dev/null 2>&1; then
        if lsof -i ":$port" -t >/dev/null 2>&1; then
            return 0  # 실행 중
        fi
    fi

    # streamlit 프로세스 + web_interface.py 조합으로 찾기
    if pgrep -f "streamlit.*web_interface.py" > /dev/null 2>&1; then
        return 0  # 실행 중
    fi

    return 1  # 실행 안 함
}

# 가상환경 찾기
find_virtualenv() {
    local candidates=(".venv" "venv" "env" ".env")

    for venv in "${candidates[@]}"; do
        if [ -d "${PROJECT_ROOT}/$venv" ]; then
            echo "$venv"
            return 0
        fi
    done

    return 1
}

# 시스템 검증
run_system_check() {
    log INFO "시스템 검증 중..."

    if python3 "${PROJECT_ROOT}/utils/system_checker.py" 2>&1 | tee -a "$LOG_FILE"; then
        log SUCCESS "시스템 검증 완료"
        return 0
    else
        local exit_code=$?
        log WARN "시스템 검증에서 경고가 발생했습니다"

        echo ""
        echo -e "${YELLOW}계속하시겠습니까? (y/n): ${NC}"
        read -r response

        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            log INFO "사용자가 취소했습니다"
            exit 0
        fi

        return 0
    fi
}

# 포트 포워딩 설정 (WSL 전용)
setup_port_forwarding() {
    # WSL 환경이 아니면 스킵
    if [ ! -f /proc/version ] || ! grep -qi microsoft /proc/version; then
        log INFO "WSL 환경이 아니므로 포트 포워딩을 건너뜁니다"
        return 0
    fi

    log INFO "WSL 포트 포워딩 설정 중..."

    if ! command -v powershell.exe &> /dev/null; then
        log WARN "PowerShell을 찾을 수 없습니다. 포트 포워딩을 건너뜁니다"
        return 0
    fi

    # PowerShell 명령 실행
    if powershell.exe -ExecutionPolicy Bypass -Command "
        # 기존 규칙 삭제
        netsh interface portproxy delete v4tov4 listenport=$PORT listenaddress=0.0.0.0 2>\$null | Out-Null

        # WSL IP 가져오기
        \$wslIp = (wsl hostname -I).Trim().Split()[0]

        if (-not \$wslIp) {
            Write-Error 'WSL IP를 가져올 수 없습니다'
            exit 1
        }

        # 포트 포워딩 추가
        netsh interface portproxy add v4tov4 listenport=$PORT listenaddress=0.0.0.0 connectport=$PORT connectaddress=\$wslIp | Out-Null

        # Windows IP 가져오기
        \$hostIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {\$_.IPAddress -notlike '127.*' -and \$_.IPAddress -notlike '169.*' -and \$_.InterfaceAlias -notlike '*WSL*'} | Select-Object -First 1).IPAddress

        Write-Host '✅ 포트 포워딩 설정 완료!' -ForegroundColor Green
        if (\$hostIp) {
            Write-Host \"   네트워크 접속: http://\$hostIp:$PORT\" -ForegroundColor Cyan
        }
    " 2>&1 | tee -a "$LOG_FILE"; then
        log SUCCESS "포트 포워딩 설정 완료"
    else
        log WARN "포트 포워딩 설정 실패 (로컬 접속은 가능합니다)"
    fi
}

# 브라우저 자동 열기 (선택 사항)
open_browser() {
    local url="$1"

    # WSL 환경에서만 자동 열기 시도
    if [ -f /proc/version ] && grep -qi microsoft /proc/version; then
        if command -v cmd.exe &> /dev/null; then
            sleep 2  # 서버 시작 대기
            cmd.exe /c start "$url" 2>/dev/null &
        fi
    fi
}

# ==================== 메인 로직 ====================

main() {
    # 에러 핸들러 설정
    trap 'error_handler $LINENO' ERR
    trap interrupt_handler INT TERM

    clear
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    🤖 AI-CHAT 시작하기 v2.0 🤖     ${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    log INFO "시작 로그: $LOG_FILE"
    log INFO "프로젝트 경로: $PROJECT_ROOT"
    echo ""

    # 1. 이미 실행 중인지 확인
    if check_running_process "$PORT"; then
        log WARN "AI-CHAT이 이미 포트 $PORT에서 실행 중입니다"
        echo ""
        echo "브라우저에서 열기: http://localhost:$PORT"
        echo ""

        echo -e "${YELLOW}재시작하시겠습니까? (y/n): ${NC}"
        read -r restart

        if [[ "$restart" == "y" || "$restart" == "Y" ]]; then
            log INFO "기존 프로세스 종료 중..."

            # 포트 사용 중인 프로세스 종료
            if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -t >/dev/null 2>&1; then
                lsof -i ":$PORT" -t | xargs kill -9 2>/dev/null || true
            fi

            # streamlit 프로세스 종료
            pkill -f "streamlit.*web_interface.py" 2>/dev/null || true

            sleep 2
            log SUCCESS "기존 프로세스 종료 완료"
        else
            log INFO "사용자가 취소했습니다"
            exit 0
        fi
    fi

    # 2. 프로젝트 디렉토리로 이동
    cd "$PROJECT_ROOT" || {
        log ERROR "프로젝트 디렉토리로 이동 실패: $PROJECT_ROOT"
        exit 1
    }

    # 3. 가상환경 활성화
    VENV_PATH=$(find_virtualenv)
    if [ -z "$VENV_PATH" ]; then
        log ERROR "가상환경을 찾을 수 없습니다"
        log ERROR "다음 명령으로 가상환경을 생성하세요: python3 -m venv .venv"
        exit 1
    fi

    log SUCCESS "Python 가상환경 활성화 ($VENV_PATH)"
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/${VENV_PATH}/bin/activate"

    # 4. 시스템 검증
    echo ""
    run_system_check

    # 5. 포트 포워딩 설정 (WSL)
    echo ""
    setup_port_forwarding

    # 6. FastAPI 백엔드 시작 (백그라운드)
    echo ""
    log INFO "FastAPI 백엔드 시작 중..."

    # 기존 API 서버 종료
    pkill -f "uvicorn.*app.api.main" 2>/dev/null || true
    sleep 1

    # FastAPI 시작 (7860 포트)
    API_PORT=7860
    .venv/bin/python -m uvicorn app.api.main:app \
        --host 0.0.0.0 \
        --port "$API_PORT" \
        --log-level info \
        > "${PROJECT_ROOT}/logs/api_$(date +%Y%m%d_%H%M%S).log" 2>&1 &

    API_PID=$!
    export API_PID

    # API 서버 시작 대기 (최대 10초)
    for i in {1..10}; do
        if curl -s "http://localhost:$API_PORT/_healthz" > /dev/null 2>&1; then
            log SUCCESS "FastAPI 서버 시작 완료 (PID: $API_PID, 포트: $API_PORT)"
            break
        fi
        sleep 1
    done

    if ! curl -s "http://localhost:$API_PORT/_healthz" > /dev/null 2>&1; then
        log WARN "FastAPI 서버 헬스체크 실패 (계속 진행)"
    fi

    # 7. Streamlit UI 실행
    echo ""
    log INFO "Streamlit UI 시작 중..."
    echo ""
    echo "========================================="
    echo "📌 접속 주소:"
    echo "   UI (Streamlit): http://localhost:$PORT"
    echo "   API (FastAPI):  http://localhost:$API_PORT"
    echo "   Health Check:   http://localhost:$API_PORT/_healthz"
    echo "   네트워크: 위에 표시된 주소 사용"
    echo "========================================="
    echo ""
    echo "종료하려면: Ctrl + C"
    echo ""

    # 브라우저 자동 열기 (백그라운드)
    # open_browser "http://localhost:$PORT" &

    # Streamlit 실행 (포어그라운드)
    log INFO "Streamlit 서버 시작..."
    streamlit run web_interface.py \
        --server.port "$PORT" \
        --server.address "$HOST" \
        --server.headless true \
        --browser.gatherUsageStats false \
        2>&1 | tee -a "$LOG_FILE"
}

# ==================== 실행 ====================

main "$@"
