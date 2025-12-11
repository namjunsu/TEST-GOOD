#!/usr/bin/env bash
# ============================================================================
# 문서 추가 스크립트
# ============================================================================
# 사용법:
#   ./scripts/ops/add_docs.sh /path/to/document.pdf
#   ./scripts/ops/add_docs.sh /path/to/folder/*.pdf
#   ./scripts/ops/add_docs.sh  # docs/incoming/ 폴더의 모든 PDF 처리
#
# 설명:
#   1. PDF를 docs/incoming/로 복사
#   2. 텍스트 추출 + 메타데이터 파싱
#   3. metadata.db에 등록
#   4. BM25 인덱스 재생성
# ============================================================================

set -Eeuo pipefail

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 경로
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

INCOMING_DIR="docs/incoming"
VENV_PYTHON=".venv/bin/python3"

log_info() { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error() { echo -e "${RED}❌ $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }

# ============================================================================
# 가상환경 확인
# ============================================================================
if [ ! -f "$VENV_PYTHON" ]; then
    log_error "가상환경이 없습니다. .venv/bin/python3를 찾을 수 없습니다."
    exit 1
fi

# ============================================================================
# 인자 처리
# ============================================================================
mkdir -p "$INCOMING_DIR"

if [ $# -gt 0 ]; then
    # 인자로 파일 경로가 주어진 경우
    for file in "$@"; do
        if [ -f "$file" ] && [[ "$file" == *.pdf || "$file" == *.PDF ]]; then
            log_info "복사 중: $file → $INCOMING_DIR/"
            cp "$file" "$INCOMING_DIR/"
        else
            log_warn "PDF 파일이 아니거나 존재하지 않음: $file"
        fi
    done
fi

# ============================================================================
# incoming 폴더 확인
# ============================================================================
PDF_COUNT=$(find "$INCOMING_DIR" -maxdepth 1 -name "*.pdf" -o -name "*.PDF" 2>/dev/null | wc -l)

if [ "$PDF_COUNT" -eq 0 ]; then
    log_warn "처리할 PDF 파일이 없습니다."
    log_info "사용법:"
    echo "  $0 /path/to/document.pdf"
    echo "  $0 /path/to/folder/*.pdf"
    echo "  또는 docs/incoming/ 폴더에 PDF를 넣고 실행"
    exit 0
fi

log_info "처리할 문서: ${PDF_COUNT}개"
echo ""

# ============================================================================
# 문서 인제스트
# ============================================================================
log_info "문서 인제스트 시작..."
$VENV_PYTHON scripts/core/ingest_from_docs.py --source "$INCOMING_DIR"

if [ $? -ne 0 ]; then
    log_error "인제스트 실패"
    exit 1
fi

# ============================================================================
# BM25 인덱스 재생성
# ============================================================================
echo ""
log_info "BM25 인덱스 재생성 중..."
$VENV_PYTHON scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index

if [ $? -ne 0 ]; then
    log_error "인덱스 재생성 실패"
    exit 1
fi

# ============================================================================
# 결과 확인
# ============================================================================
echo ""
log_success "문서 추가 완료!"

# 현재 문서 수 확인
TOTAL_DOCS=$($VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
count = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
print(count)
conn.close()
")

log_info "현재 총 문서 수: ${TOTAL_DOCS}개"
log_info "Streamlit 앱을 재시작하면 새 문서가 반영됩니다."
