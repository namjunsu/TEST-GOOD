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
    INFO)    printf "\033[0;32mℹ️  %s\033[0m\n" "$msg" ;;
    WARN)    printf "\033[1;33m⚠️  %s\033[0m\n" "$msg" ;;
    ERROR)   printf "\033[0;31m❌ %s\033[0m\n" "$msg" ;;
    SUCCESS) printf "\033[0;32m✅ %s\033[0m\n" "$msg" ;;
    *)       printf "%s\n" "$msg" ;;
  esac
}

# ---------- 외부 환경 충돌 최소화 ----------
unset MODEL_PATH CHAT_FORMAT N_CTX N_GPU_LAYERS LLM_MODEL_PATH QWEN_MODEL_PATH 2>/dev/null || true
log INFO "외부 환경변수 핵심 키 초기화 완료"

# ---------- .env 로드 ----------
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; # export all
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  log INFO ".env 로드: $ENV_FILE"
else
  log WARN ".env 파일이 없습니다: $ENV_FILE"
fi

# ---------- 필수 변수/파일 검증 ----------
PORT="${AI_CHAT_PORT:-8501}"
HOST="${AI_CHAT_HOST:-0.0.0.0}"
API_PORT="${AI_CHAT_API_PORT:-7860}"

: "${MODEL_PATH:?MODEL_PATH가 비어있습니다 (.env 확인)}"
[[ -f "$MODEL_PATH" ]] || { log ERROR "MODEL_PATH 파일 없음: $MODEL_PATH"; exit 2; }

: "${RETRIEVER_BACKEND:=bm25}"
if [[ "$RETRIEVER_BACKEND" == "bm25" ]]; then
  : "${BM25_INDEX_PATH:?BM25_INDEX_PATH가 비어있습니다 (.env 확인)}"
  [[ -f "$BM25_INDEX_PATH" ]] || log WARN "BM25 인덱스 파일이 아직 없습니다: $BM25_INDEX_PATH"
fi
log INFO "MODEL_PATH 적용: $(basename "$MODEL_PATH")"
log INFO "RETRIEVER_BACKEND: $RETRIEVER_BACKEND"

# ---------- BM25 인덱스 가드 (존재/정합성/자동복구) ----------
if [[ "$RETRIEVER_BACKEND" == "bm25" ]]; then
  log INFO "BM25 인덱스 가드 실행: ${BM25_INDEX_PATH}"

  # 1. 인덱스 파일 존재 확인
  if [[ ! -f "${BM25_INDEX_PATH}" ]]; then
    log WARN "BM25 인덱스가 없어 재인덱싱을 수행합니다"
    python scripts/reindex_atomic.py || {
      log ERROR "재인덱싱 실패"
      exit 1
    }
  fi

  # 2. 메타DB vs BM25 문서 수 정합성 (허용 편차 5% 또는 10문서 중 큰 값)
  python - <<'PYCHECK'
import sqlite3, os, sys
from app.index.bm25_store import BM25Store

try:
    index_path = os.environ.get("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
    bm = BM25Store(index_path=index_path)
    b = bm.N
    c = sqlite3.connect("metadata.db").execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    thr = max(int(c * 0.05), 10)
    print(f"BM25={b}, META={c}, THR={thr}", flush=True)
    sys.exit(0 if abs(b - c) <= thr else 2)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYCHECK
  rc=$?
  if [[ $rc -eq 2 ]]; then
    log WARN "인덱스 드리프트 감지 → 재인덱싱"
    python scripts/reindex_atomic.py || {
      log ERROR "재인덱싱 실패"
      exit 1
    }
  elif [[ $rc -ne 0 ]]; then
    log ERROR "인덱스 정합성 검증 실패 (rc=$rc)"
    exit 1
  fi

  log SUCCESS "BM25 인덱스 가드 통과"
fi

# ---------- 락 파일(동시 실행 방지) ----------
LOCK_DIR="${PROJECT_ROOT}/var/run"; mkdir -p "$LOCK_DIR"
LOCK_FILE="${LOCK_DIR}/ai-chat.lock"
exec 9>"$LOCK_FILE" || { log ERROR "lockfile 열기 실패: $LOCK_FILE"; exit 1; }
if ! flock -n 9; then
  log ERROR "다른 인스턴스가 실행 중입니다. ($LOCK_FILE)"
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
log SUCCESS "가상환경 감지: ${VENV_DIR}"

# ---------- 에러/인터럽트/종료 핸들러 ----------
API_PID=""
cleanup() {
  log INFO "정리 작업 시작..."
  if [[ -n "${API_PID}" ]] && ps -p "$API_PID" >/dev/null 2>&1; then
    log INFO "FastAPI 종료 (PID: $API_PID)"
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  # 정확 매칭: 현재 프로젝트 루트 기준 uvicorn 종료(오살 최소화)
  pgrep -fa "uvicorn app\.api\.main:app" | awk '{print $1}' | xargs -r kill 2>/dev/null || true
  log SUCCESS "정리 완료"
}
trap 'log ERROR "스크립트 오류(라인 $LINENO)"; cleanup; exit 1' ERR
trap 'log WARN "사용자 중단"; cleanup; exit 130' INT TERM
trap 'cleanup' EXIT

# ---------- 시스템 사전 점검 ----------
if [[ -x "${PROJECT_ROOT}/utils/system_checker.py" ]]; then
  log INFO "시스템 검증 실행..."
  if ! "${PY}" "${PROJECT_ROOT}/utils/system_checker.py" 2>&1 | tee -a "$LOG_FILE"; then
    log WARN "시스템 검증 경고. 계속 진행할지 선택하세요."
    read -r -p "계속 진행(y)/중단(n): " ans
    [[ "${ans:-n}" =~ ^[Yy]$ ]] || { log INFO "사용자 선택으로 종료"; exit 0; }
  else
    log SUCCESS "시스템 검증 통과"
  fi
fi

# ---------- WSL 포트 프록시(선택) ----------
setup_port_forwarding() {
  if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
    log INFO "WSL 포트 프록시 설정"
    local wsl_ip
    wsl_ip="$(hostname -I | awk '{print $1}')"
    if command -v powershell.exe >/dev/null 2>&1; then
      powershell.exe -ExecutionPolicy Bypass -Command "
        netsh interface portproxy delete v4tov4 listenport=$PORT listenaddress=0.0.0.0 2>\$null | Out-Null
        netsh interface portproxy add v4tov4 listenport=$PORT listenaddress=0.0.0.0 connectport=$PORT connectaddress=$wsl_ip | Out-Null
        Write-Host '✅ PortProxy ready on $wsl_ip:$PORT'
      " 2>&1 | tee -a "$LOG_FILE" >/dev/null
      log SUCCESS "WSL 포트 프록시 설정 완료"
    else
      log WARN "PowerShell 미탐지. 포트 프록시 건너뜀"
    fi
  else
    log INFO "WSL 아님. 포트 프록시 스킵"
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

log INFO "프로젝트 경로: ${PROJECT_ROOT}"
log INFO "로그 파일: ${LOG_FILE}"

if check_running; then
  log WARN "포트 ${PORT}에서 이미 실행 중으로 감지"
  read -r -p "재시작하시겠습니까? (y/n): " rs
  if [[ "${rs:-n}" =~ ^[Yy]$ ]]; then
    # 해당 포트 사용 프로세스만 종료
    command -v lsof >/dev/null 2>&1 && lsof -i ":${PORT}" -t | xargs -r kill -9 2>/dev/null || true
    pgrep -f "streamlit.*web_interface\.py" | xargs -r kill 2>/dev/null || true
    log SUCCESS "기존 프로세스 종료"
  else
    log INFO "사용자 선택으로 종료"
    exit 0
  fi
fi

# ---------- API 기동 ----------
log INFO "FastAPI 백엔드 시작..."
# 정확 경로/모듈 사용
"${PY}" -m uvicorn app.api.main:app --host 0.0.0.0 --port "${API_PORT}" --log-level info \
  > "${LOG_DIR}/api_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
API_PID=$!
sleep 2

# 헬스체크
for _ in {1..12}; do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    log SUCCESS "FastAPI 헬시 (PID: $API_PID, :${API_PORT})"
    break
  fi
  sleep 1
done
if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  log WARN "API 헬스체크 실패"
  read -r -p "계속 진행(y)/중단(n): " c
  [[ "${c:-n}" =~ ^[Yy]$ ]] || { log INFO "사용자 선택으로 종료"; exit 1; }
fi

# ---------- WSL 포트 프록시 ----------
setup_port_forwarding

# ---------- UI 기동 ----------
log INFO "Streamlit UI 시작..."
echo "========================================="
echo "UI:  http://localhost:${PORT}"
echo "API: http://localhost:${API_PORT}"
echo "Health: http://localhost:${API_PORT}/health"
echo "========================================="

exec "${ST}" run web_interface.py \
  --server.port "${PORT}" \
  --server.address "${HOST}" \
  --server.headless true \
  --browser.gatherUsageStats false 2>&1 | tee -a "$LOG_FILE"
