#!/usr/bin/env bash
# ============================================================================
# AI-CHAT 재색인 스크립트
# ============================================================================
# 기능:
# - 문서 인덱스 재생성
# - 메타데이터 DB 업데이트
# - 파일락으로 동시 실행 방지
# ============================================================================

set -Eeuo pipefail

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

# 경로
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

LOCK_FILE="var/db/reindex.lock"

log_info() { echo -e "${GREEN}ℹ️  $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error() { echo -e "${RED}❌ $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }

# ============================================================================
# 파일락 확인
# ============================================================================

if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        log_error "이미 재색인이 실행 중입니다 (PID: $PID)"
        exit 1
    else
        log_warn "오래된 락 파일 제거 (PID $PID는 실행 중이 아님)"
        rm -f "$LOCK_FILE"
    fi
fi

# 락 파일 생성
echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# ============================================================================
# 가상환경 활성화
# ============================================================================

if [ ! -d .venv ]; then
    log_error "가상환경이 없습니다."
    exit 1
fi

source .venv/bin/activate

# ============================================================================
# 재색인 실행
# ============================================================================

log_info "문서 재색인 시작..."
echo ""

# auto_indexer.py 또는 rebuild 스크립트 실행
if [ -f "app/indexer/cli.py" ]; then
    log_info "app/indexer/cli.py 실행 중..."
    python3 -m app.indexer.cli --rebuild
elif [ -f "rebuild_rag_indexes.py" ]; then
    log_info "rebuild_rag_indexes.py 실행 중..."
    python3 rebuild_rag_indexes.py
else
    log_error "재색인 스크립트를 찾을 수 없습니다."
    exit 1
fi

echo ""
log_success "재색인 완료!"
log_info "Streamlit 앱을 재시작하여 새 인덱스를 로드하세요."
