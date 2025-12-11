#!/usr/bin/env bash
# =============================================
# AI-CHAT 실행 스크립트 (안전 보강 v2.1)
# =============================================
set -Eeuo pipefail
IFS=$'\n\t'

# ---------- 공통 설정 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/start_$(date +%Y%m%d_%H%M%S).log"

# 단일 로그 함수
log() {
  local level="$1"; shift
  local msg="$*"
  local ts
  ts="$(date +'%Y-%m-%d %H:%M:%S')"
  echo "[$ts] [$level] $msg" >> "$LOG_FILE"
  case "$level" in
    INFO)    printf "\033[0;90mℹ️  %s\033[0m\n" "$msg" ;;
    WARN)    printf "\033[1;33m⚠️  %s\033[0m\n" "$msg" ;;
    ERROR)   printf "\033[0;31m❌ %s\033[0m\n" "$msg" ;;
    SUCCESS) printf "\033[0;32m✅ %s\033[0m\n" "$msg" ;;
    QUIET)   ;;  # 파일에만 기록, 터미널 출력 없음
    *)       printf "%s\n" "$msg" ;;
  esac
}

# 스피너 함수
spin() {
  local pid=$1
  local msg=$2
  local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  tput civis 2>/dev/null || true  # 커서 숨기기
  while kill -0 "$pid" 2>/dev/null; do
    for ((i=0; i<${#chars}; i++)); do
      printf "\r\033[0;36m%s\033[0m %s" "${chars:$i:1}" "$msg"
      sleep 0.08
    done
  done
  printf "\r\033[K"  # 라인 클리어
  tput cnorm 2>/dev/null || true  # 커서 복원
}

# 스피너와 함께 명령 실행
run_with_spinner() {
  local msg=$1
  shift
  "$@" >> "$LOG_FILE" 2>&1 &
  local pid=$!
  spin $pid "$msg"
  wait $pid
  return $?
}

# ASCII 로고 표시
show_logo() {
  printf "\033[0;36m"
  cat << 'EOF'

   █████╗ ██╗      ██████╗██╗  ██╗ █████╗ ████████╗
  ██╔══██╗██║     ██╔════╝██║  ██║██╔══██╗╚══██╔══╝
  ███████║██║     ██║     ███████║███████║   ██║
  ██╔══██║██║     ██║     ██╔══██║██╔══██║   ██║
  ██║  ██║███████╗╚██████╗██║  ██║██║  ██║   ██║
  ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
EOF
  printf "\033[0m"
  printf "\033[0;90m                                      v1.0 · RAG System\033[0m\n"
  echo ""
}

# 시스템 정보 표시
show_system_info() {
  local cpu_model mem_total mem_used mem_pct model_name doc_count

  cpu_model=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Unknown")
  mem_total=$(free -h 2>/dev/null | awk '/Mem:/ {print $2}' || echo "?")
  mem_used=$(free -h 2>/dev/null | awk '/Mem:/ {print $3}' || echo "?")
  mem_pct=$(free 2>/dev/null | awk '/Mem:/ {printf "%.0f", $3/$2*100}' || echo "?")
  model_name=$(basename "${MODEL_PATH:-unknown}")
  doc_count=$(sqlite3 "${PROJECT_ROOT}/metadata.db" "SELECT COUNT(*) FROM documents" 2>/dev/null || echo "?")

  printf "\033[0;90m"
  echo "  ┌─────────────────────────────────────────────────┐"
  printf "  │  \033[0;37mCPU:\033[0;90m    %-38s │\n" "${cpu_model:0:38}"
  printf "  │  \033[0;37mMemory:\033[0;90m %-17s \033[0;90m(%s%%)\033[0;90m               │\n" "${mem_used} / ${mem_total}" "${mem_pct}"
  printf "  │  \033[0;37mModel:\033[0;90m  %-38s │\n" "${model_name:0:38}"
  printf "  │  \033[0;37mDocs:\033[0;90m   %-38s │\n" "${doc_count}개"
  echo "  └─────────────────────────────────────────────────┘"
  printf "\033[0m"
  echo ""
}

# 타이핑 애니메이션
type_text() {
  local text="$1"
  local delay="${2:-0.02}"
  for ((i=0; i<${#text}; i++)); do
    printf "%s" "${text:$i:1}"
    sleep "$delay"
  done
}

# ---------- 외부 환경 충돌 최소화 ----------
unset MODEL_PATH CHAT_FORMAT N_CTX N_GPU_LAYERS LLM_MODEL_PATH QWEN_MODEL_PATH BM25_INDEX_PATH 2>/dev/null || true
log QUIET "외부 환경변수 핵심 키 초기화 완료"

# ---------- .env 로드 ----------
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; # export all
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  log QUIET ".env 로드: $ENV_FILE"
else
  log WARN ".env 파일이 없습니다: $ENV_FILE"
fi

# ---------- 필수 변수/파일 검증 ----------
PORT="${AI_CHAT_PORT:-8501}"
HOST="${AI_CHAT_HOST:-0.0.0.0}"
API_PORT="${AI_CHAT_API_PORT:-7860}"
PY="${PROJECT_ROOT}/.venv/bin/python"

: "${MODEL_PATH:?MODEL_PATH가 비어있습니다 (.env 확인)}"
[[ -f "$MODEL_PATH" ]] || { log ERROR "MODEL_PATH 파일 없음: $MODEL_PATH"; exit 2; }

: "${RETRIEVER_BACKEND:=bm25}"
if [[ "$RETRIEVER_BACKEND" == "bm25" ]]; then
  : "${BM25_INDEX_PATH:?BM25_INDEX_PATH가 비어있습니다 (.env 확인)}"
  [[ -f "$BM25_INDEX_PATH" ]] || log WARN "BM25 인덱스 파일이 아직 없습니다: $BM25_INDEX_PATH"
fi
log QUIET "MODEL_PATH 적용: $(basename "$MODEL_PATH")"
log QUIET "RETRIEVER_BACKEND: $RETRIEVER_BACKEND"

# ---------- 시작 화면 표시 ----------
clear
show_logo
show_system_info

# ---------- 연도 폴더 → incoming 동기화 + 인제스트 ----------
# 기본값: 자동 실행 비활성화 (순환 복사 방지)
# 필요 시 ENABLE_AUTO_SYNC=1 환경변수로 활성화
if [[ "${ENABLE_AUTO_SYNC:-0}" == "1" ]]; then
  if run_with_spinner "문서 동기화 중..." "${PY}" scripts/sync_year_docs_to_incoming.py; then
    log SUCCESS "문서 동기화 완료"
  else
    log WARN "동기화 중 경고 발생 (계속 진행)"
  fi

  if run_with_spinner "문서 인제스트 중..." "${PY}" scripts/ingest_from_docs.py; then
    log SUCCESS "인제스트 완료"
  else
    log WARN "인제스트 중 경고 발생 (계속 진행)"
  fi
fi

# ---------- BM25 인덱스 가드 (존재/정합성/자동복구) ----------
if [[ "$RETRIEVER_BACKEND" == "bm25" && "${SKIP_BM25_GUARD:-0}" != "1" ]]; then
  printf "\033[0;36m⠋\033[0m BM25 인덱스 검증 중..."

  # 1. 인덱스 파일 존재 확인
  if [[ ! -f "${BM25_INDEX_PATH}" ]]; then
    printf "\r\033[K"
    log WARN "BM25 인덱스가 없어 재인덱싱을 수행합니다"
    if run_with_spinner "BM25 인덱스 생성 중..." python scripts/data/indexing/rebuild_bm25.py; then
      log SUCCESS "BM25 인덱스 생성 완료"
    else
      log ERROR "재인덱싱 실패"
      exit 1
    fi
  fi

  # 2. 메타DB vs BM25 문서 수 정합성 (허용 편차 5% 또는 10문서 중 큰 값)
  set +e  # 일시적으로 exit-on-error 비활성화
  BM25_CHECK_OUTPUT=$(PYTHONPATH="${PROJECT_ROOT}" python - 2>>"${LOG_FILE}" <<'PYCHECK'
import sqlite3, os, sys, logging
logging.disable(logging.CRITICAL)  # 로거 출력 억제
from rag_system.active.bm25_store import BM25Store

try:
    index_path = os.environ.get("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
    bm = BM25Store(index_path=index_path)
    b = len(bm.documents)
    c = sqlite3.connect("metadata.db").execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    thr = max(int(c * 0.05), 10)
    print(f"{b}", flush=True)  # 문서 수만 출력
    sys.exit(0 if abs(b - c) <= thr else 2)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYCHECK
)
  rc=$?
  set -e  # exit-on-error 재활성화

  printf "\r\033[K"  # 스피너 라인 클리어

  if [[ $rc -eq 2 ]]; then
    log WARN "인덱스 드리프트 감지 → 재인덱싱"
    if run_with_spinner "BM25 재인덱싱 중..." python scripts/data/indexing/rebuild_bm25.py; then
      log SUCCESS "BM25 재인덱싱 완료"
    else
      log ERROR "재인덱싱 실패"
      exit 1
    fi
  elif [[ $rc -ne 0 ]]; then
    log ERROR "인덱스 정합성 검증 실패 (상세: ${LOG_FILE})"
    exit 1
  else
    log SUCCESS "BM25 인덱스 검증 완료 (${BM25_CHECK_OUTPUT}개 문서)"
  fi
fi

# ---------- 기존 프로세스 자동 종료 ----------
EXISTING_PIDS=$(pgrep -f "uvicorn app.api.main|streamlit run web_interface.py" 2>/dev/null | tr '\n' ' ' || true)
if [[ -n "$EXISTING_PIDS" ]]; then
  log WARN "기존 프로세스 발견, 종료 중..."
  pkill -f "uvicorn app.api.main" 2>/dev/null || true
  pkill -f "streamlit run web_interface.py" 2>/dev/null || true
  sleep 2
fi

# ---------- 락 파일(동시 실행 방지) ----------
LOCK_DIR="${PROJECT_ROOT}/var/run"; mkdir -p "$LOCK_DIR"
LOCK_FILE="${LOCK_DIR}/ai-chat.lock"
# 기존 lock 파일 제거 (stale lock 방지)
rm -f "$LOCK_FILE" 2>/dev/null || true
exec 9>"$LOCK_FILE" || { log ERROR "lockfile 열기 실패: $LOCK_FILE"; exit 1; }
if ! flock -n 9; then
  log ERROR "락 파일 획득 실패 ($LOCK_FILE)"
  exit 1
fi

# ---------- 가상환경 탐색 ----------
find_virtualenv() {
  local cands=(".venv" "venv" "env")
  for v in "${cands[@]}"; do
    [[ -x "${PROJECT_ROOT}/${v}/bin/python" ]] && { echo "$v"; return 0; }
  done
  return 1
}
VENV_DIR="$(find_virtualenv || true)"
if [[ -z "${VENV_DIR:-}" ]]; then
  log ERROR "가상환경을 찾지 못했습니다. 다음으로 생성: python3 -m venv .venv && . .venv/bin/activate"
  exit 1
fi
VENV_BIN="${PROJECT_ROOT}/${VENV_DIR}/bin"
PY="${VENV_BIN}/python"
ST="${VENV_BIN}/streamlit"
UVICORN="${VENV_BIN}/uvicorn"
log QUIET "가상환경 감지: ${VENV_DIR}"

# ---------- 에러/인터럽트/종료 핸들러 ----------
API_PID=""
UI_PID=""
CLEANUP_DONE=0
cleanup() {
  # 중복 실행 방지
  [[ $CLEANUP_DONE -eq 1 ]] && return
  CLEANUP_DONE=1

  # trap 해제 (무한 반복 방지)
  trap - ERR INT TERM EXIT

  log INFO "정리 작업 시작..."

  # UI 프로세스 종료 (프로세스 그룹 포함)
  if [[ -n "${UI_PID}" ]] && ps -p "$UI_PID" >/dev/null 2>&1; then
    log INFO "Streamlit 종료 (PID: $UI_PID)"
    local pgid
    pgid=$(ps -o pgid= -p "$UI_PID" 2>/dev/null | tr -d ' ') || pgid=""
    if [[ -n "$pgid" ]]; then
      kill -- -"$pgid" 2>/dev/null || true
    fi
    kill "$UI_PID" 2>/dev/null || true
    wait "$UI_PID" 2>/dev/null || true
  fi

  # API 프로세스 종료 (프로세스 그룹 포함)
  if [[ -n "${API_PID}" ]] && ps -p "$API_PID" >/dev/null 2>&1; then
    log INFO "FastAPI 종료 (PID: $API_PID)"
    local pgid
    pgid=$(ps -o pgid= -p "$API_PID" 2>/dev/null | tr -d ' ') || pgid=""
    if [[ -n "$pgid" ]]; then
      kill -- -"$pgid" 2>/dev/null || true
    fi
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi

  # 잔여 프로세스 종료
  pgrep -fa "uvicorn app\.api\.main:app" | awk '{print $1}' | xargs -r kill 2>/dev/null || true
  pgrep -fa "streamlit.*web_interface\.py" | awk '{print $1}' | xargs -r kill 2>/dev/null || true

  log SUCCESS "정리 완료"
}
trap 'log ERROR "스크립트 오류(라인 $LINENO)"; cleanup; exit 1' ERR
trap 'log WARN "사용자 중단"; cleanup; exit 130' INT TERM
trap 'cleanup' EXIT

# ---------- 시스템 사전 점검 ----------
if [[ -x "${PROJECT_ROOT}/utils/system_checker.py" ]]; then
  if ! "${PY}" "${PROJECT_ROOT}/utils/system_checker.py" >> "$LOG_FILE" 2>&1; then
    log WARN "시스템 검증 경고 (상세: ${LOG_FILE})"
    if [[ "${ASSUME_YES:-0}" != "1" ]]; then
      read -r -p "계속 진행(y)/중단(n): " ans
      [[ "${ans:-n}" =~ ^[Yy]$ ]] || { log INFO "사용자 선택으로 종료"; exit 0; }
    fi
  fi
fi

# ---------- WSL 포트 프록시(선택) ----------
setup_port_forwarding() {
  if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
    local wsl_ip
    wsl_ip="$(hostname -I | awk '{print $1}')"
    if command -v powershell.exe >/dev/null 2>&1; then
      powershell.exe -ExecutionPolicy Bypass -Command "
        netsh interface portproxy delete v4tov4 listenport=$PORT listenaddress=0.0.0.0 2>\$null | Out-Null
        netsh interface portproxy add v4tov4 listenport=$PORT listenaddress=0.0.0.0 connectport=$PORT connectaddress=$wsl_ip | Out-Null
      " >> "$LOG_FILE" 2>&1 || true
    fi
  fi
}

# ---------- 이미 실행 중인지 확인 ----------
check_running() {
  # 포트 프로세스 탐지 (lsof 우선)
  if command -v lsof >/dev/null 2>&1 && lsof -i ":${PORT}" -t >/dev/null 2>&1; then
    return 0
  fi
  pgrep -f "streamlit.*web_interface\.py" >/dev/null 2>&1 && return 0
  return 1
}

log QUIET "프로젝트 경로: ${PROJECT_ROOT}"
log QUIET "로그 파일: ${LOG_FILE}"

if check_running; then
  log WARN "포트 ${PORT}에서 이미 실행 중"
  if [[ "${ASSUME_YES:-0}" == "1" ]]; then
    rs="y"
  else
    read -r -p "재시작하시겠습니까? (y/n): " rs
  fi
  if [[ "${rs:-n}" =~ ^[Yy]$ ]]; then
    command -v lsof >/dev/null 2>&1 && lsof -i ":${PORT}" -t | xargs -r kill -9 2>/dev/null || true
    pgrep -f "streamlit.*web_interface\.py" | xargs -r kill 2>/dev/null || true
  else
    exit 0
  fi
fi

# ---------- LLM 모델 사전 로드 ----------
LLM_LOG="${LOG_DIR}/llm_preload_$(date +%Y%m%d_%H%M%S).log"
PYTHONPATH="${PROJECT_ROOT}" "${PY}" scripts/preload_llm.py > "$LLM_LOG" 2>&1 &
LLM_PID=$!
spin $LLM_PID "LLM 모델 로드 중..."
wait $LLM_PID
LLM_RC=$?
if [[ $LLM_RC -eq 0 ]]; then
  log SUCCESS "LLM 모델 로드 완료"
else
  log WARN "LLM 로드 실패 (첫 질의 시 느릴 수 있음)"
fi

# ---------- API 기동 ----------
"${PY}" -m uvicorn app.api.main:app --host 0.0.0.0 --port "${API_PORT}" --log-level warning \
  > "${LOG_DIR}/api_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
API_PID=$!

# 헬스체크 (스피너)
API_HEALTHY=0
{
  for _ in {1..15}; do
    if curl -sf "http://127.0.0.1:${API_PORT}/_healthz" >/dev/null 2>&1; then
      exit 0
    fi
    sleep 1
  done
  exit 1
} &
HEALTH_PID=$!
spin $HEALTH_PID "FastAPI 시작 중..."
wait $HEALTH_PID && API_HEALTHY=1

if [[ $API_HEALTHY -eq 1 ]]; then
  log SUCCESS "FastAPI 준비 완료 (PID: $API_PID)"
else
  log WARN "API 헬스체크 타임아웃 (계속 진행)"
fi

# ---------- WSL 포트 프록시 ----------
setup_port_forwarding

# ---------- UI 기동 ----------
printf "\033[0;36m⠋\033[0m Streamlit UI 시작 중..."
"${ST}" run web_interface.py \
  --server.port "${PORT}" \
  --server.address "${HOST}" \
  --server.headless true \
  --browser.gatherUsageStats false >> "$LOG_FILE" &
UI_PID=$!
sleep 3
printf "\r\033[K"

# 최종 상태 출력
echo ""
printf "\033[0;32m"
type_text "  ✅ 준비 완료!" 0.04
printf "\033[0m\n"
echo ""
printf "\033[0;36m  ╔═══════════════════════════════════════╗\033[0m\n"
printf "\033[0;36m  ║\033[0m  \033[1mUI\033[0m:     http://localhost:%-12s\033[0;36m║\033[0m\n" "${PORT}"
printf "\033[0;36m  ║\033[0m  \033[1mAPI\033[0m:    http://localhost:%-12s\033[0;36m║\033[0m\n" "${API_PORT}"
printf "\033[0;36m  ╚═══════════════════════════════════════╝\033[0m\n"
echo ""
printf "\033[0;90m  로그: %s\033[0m\n" "${LOG_FILE}"
printf "\033[0;90m  Ctrl+C로 종료\033[0m\n"
echo ""

wait "$UI_PID"
UI_RC=$?

log QUIET "Streamlit 종료 (exit code: $UI_RC)"
exit "$UI_RC"
