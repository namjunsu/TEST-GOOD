#!/usr/bin/env bash
#
# AI-CHAT 서비스 시작 스크립트
#
# 사용법:
#   bash ops/start_services.sh
#   bash ops/start_services.sh --check-only  # 상태 확인만
#
# NOTE:
# 이 스크립트는 "서비스 프로세스(API/Streamlit)만" 시작합니다.
# 문서 동기화/인덱싱(ingest_from_docs.py, sync_year_docs_to_incoming.py 등)은
# 별도 스크립트에서 수행해야 합니다.
#

set -euo pipefail

# 작업 디렉토리를 프로젝트 루트로 변경
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

echo "================================================================================
                      AI-CHAT 서비스 시작
================================================================================"
echo "프로젝트 루트: $PROJECT_ROOT"

# .venv 및 실행 파일 존재 체크
if [ ! -x ".venv/bin/uvicorn" ] || [ ! -x ".venv/bin/streamlit" ]; then
    echo "❌ .venv 환경 또는 uvicorn/streamlit 실행 파일을 찾을 수 없습니다."
    echo "   먼저 가상환경 생성 및 pip install 을 완료해야 합니다:"
    echo "   python -m venv .venv"
    echo "   .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# 환경 변수 로드
if [ -f .env ]; then
    echo "✓ .env 파일 로드 중..."
    set -a
    source .env
    set +a
else
    echo "⚠️  .env 파일 없음 (기본값 사용)"
fi

# 상태 확인 전용 모드
if [ "${1:-}" = "--check-only" ]; then
    echo ""
    echo "=== 프로세스 상태 ==="
    pgrep -fa "uvicorn|streamlit" || echo "실행 중인 서비스 없음"

    echo ""
    echo "=== 포트 상태 ==="
    ss -lntp 2>/dev/null | grep -E ':7860|:8501' || echo "7860, 8501 포트 사용 안함"

    exit 0
fi

# 기존 프로세스 종료
echo ""
echo "=== 기존 서비스 종료 ==="
pkill -f "uvicorn.*app.api.main" 2>/dev/null && echo "✓ uvicorn 종료" || echo "  uvicorn 미실행"
pkill -f "streamlit.*web_interface" 2>/dev/null && echo "✓ streamlit 종료" || echo "  streamlit 미실행"

# 프로세스 종료 대기
sleep 2

# API 서비스 시작
echo ""
echo "=== FastAPI 시작 (port 7860) ==="
nohup .venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 7860 \
  > /tmp/api.log 2>&1 &

API_PID=$!
echo "  PID: $API_PID"
sleep 2

# API 헬스체크 (HTTP 기반)
echo "  → API 헬스체크 (/_healthz)..."
RETRY_COUNT=0
MAX_RETRIES=10
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf "http://127.0.0.1:7860/_healthz" >/dev/null 2>&1; then
        echo "  ✓ FastAPI 시작 및 헬스체크 통과"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "  ❌ FastAPI 헬스체크 실패 (/_healthz)"
        echo "  로그: tail -n 50 /tmp/api.log"
        exit 1
    fi
    sleep 1
done

# UI 서비스 시작
echo ""
echo "=== Streamlit 시작 (port 8501) ==="
nohup .venv/bin/streamlit run web_interface.py \
  --server.port 8501 \
  --server.headless true \
  > /tmp/ui.log 2>&1 &

UI_PID=$!
echo "  PID: $UI_PID"
sleep 3

# UI 헬스체크 (HTTP 기반)
echo "  → Streamlit 헬스체크 (port 8501)..."
RETRY_COUNT=0
MAX_RETRIES=15
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf "http://127.0.0.1:8501" >/dev/null 2>&1; then
        echo "  ✓ Streamlit 시작 및 헬스체크 통과"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "  ❌ Streamlit 헬스체크 실패 (port 8501)"
        echo "  로그: tail -n 50 /tmp/ui.log"
        exit 1
    fi
    sleep 1
done

# 최종 상태 확인
echo ""
echo "================================================================================"
echo "                          ✓ 서비스 시작 완료"
echo "================================================================================"
echo ""
echo "📍 접속 URL:"
echo "   API:  http://localhost:7860"
echo "   UI:   http://localhost:8501"
echo ""
echo "📝 로그 확인:"
echo "   API:  tail -f /tmp/api.log"
echo "   UI:   tail -f /tmp/ui.log"
echo ""
echo "🔍 상태 확인:"
echo "   bash ops/start_services.sh --check-only"
echo ""
echo "🛑 종료:"
echo "   모두 종료:  pkill -f 'uvicorn|streamlit'"
echo "   개별 종료:"
echo "     kill $API_PID  # API 서버만"
echo "     kill $UI_PID   # UI 서버만"
echo ""
echo "================================================================================"

# 포트 확인
echo "=== 포트 확인 ==="
ss -lntp 2>/dev/null | grep -E ':7860|:8501' || echo "⚠️  7860/8501 포트에서 리스닝 중인 프로세스를 찾지 못했습니다."

exit 0
