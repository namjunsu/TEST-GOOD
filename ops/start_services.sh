#!/usr/bin/env bash
#
# AI-CHAT 서비스 시작 스크립트
#
# 사용법:
#   bash ops/start_services.sh
#   bash ops/start_services.sh --check-only  # 상태 확인만
#

set -euo pipefail

# 작업 디렉토리를 프로젝트 루트로 변경
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

echo "================================================================================
                      AI-CHAT 서비스 시작
================================================================================"
echo "프로젝트 루트: $PROJECT_ROOT"

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

# API 헬스체크
if pgrep -f "uvicorn.*app.api.main" > /dev/null; then
    echo "  ✓ FastAPI 시작 완료"
else
    echo "  ❌ FastAPI 시작 실패"
    echo "  로그: tail /tmp/api.log"
    exit 1
fi

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

# UI 헬스체크
if pgrep -f "streamlit.*web_interface" > /dev/null; then
    echo "  ✓ Streamlit 시작 완료"
else
    echo "  ❌ Streamlit 시작 실패"
    echo "  로그: tail /tmp/ui.log"
    exit 1
fi

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
echo "   pkill -f 'uvicorn|streamlit'"
echo ""
echo "================================================================================"

# 포트 확인
echo "=== 포트 확인 ==="
ss -lntp 2>/dev/null | grep -E ':7860|:8501' || echo "⚠️  포트 확인 실패"

exit 0
