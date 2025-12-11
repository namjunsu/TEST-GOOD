#!/usr/bin/env bash
# ============================================================================
# 문서 삭제 스크립트
# ============================================================================
# 사용법:
#   ./scripts/ops/delete_doc.sh "2024-01-15_장비구매_기안서.pdf"
#   ./scripts/ops/delete_doc.sh --id 123
#   ./scripts/ops/delete_doc.sh --search "UPS 구매"
#
# 설명:
#   1. 문서 검색/확인
#   2. 사용자 확인 후 삭제
#   3. metadata.db에서 제거
#   4. 관련 파일 삭제 (PDF, txt)
#   5. BM25 인덱스 재생성
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

VENV_PYTHON=".venv/bin/python3"
EXTRACTED_DIR="data/extracted"
QUARANTINE_DIR="docs/quarantine"

log_info() { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error() { echo -e "${RED}❌ $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }

show_usage() {
    echo "사용법:"
    echo "  $0 \"파일명.pdf\"           # 파일명으로 삭제"
    echo "  $0 --id 123               # DB ID로 삭제"
    echo "  $0 --search \"검색어\"      # 검색 후 선택 삭제"
    echo "  $0 --list                 # 삭제 가능한 문서 목록"
    echo ""
    echo "옵션:"
    echo "  --force    확인 없이 삭제"
    echo "  --no-backup  백업 없이 완전 삭제 (주의!)"
}

# ============================================================================
# 가상환경 확인
# ============================================================================
if [ ! -f "$VENV_PYTHON" ]; then
    log_error "가상환경이 없습니다."
    exit 1
fi

# ============================================================================
# 인자 파싱
# ============================================================================
FILENAME=""
DOC_ID=""
SEARCH_TERM=""
FORCE=false
NO_BACKUP=false
LIST_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --id)
            DOC_ID="$2"
            shift 2
            ;;
        --search)
            SEARCH_TERM="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --no-backup)
            NO_BACKUP=true
            shift
            ;;
        --list)
            LIST_MODE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            FILENAME="$1"
            shift
            ;;
    esac
done

# ============================================================================
# 목록 모드
# ============================================================================
if [ "$LIST_MODE" = true ]; then
    log_info "문서 목록 (최근 20개):"
    $VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cursor = conn.execute('''
    SELECT id, filename, date, drafter
    FROM documents
    ORDER BY id DESC
    LIMIT 20
''')
print(f'{'ID':>5} | {'날짜':^12} | {'작성자':^8} | 파일명')
print('-' * 80)
for row in cursor:
    id, fn, date, drafter = row
    date = date or '-'
    drafter = drafter or '-'
    print(f'{id:>5} | {date:^12} | {drafter:^8} | {fn}')
conn.close()
"
    exit 0
fi

# ============================================================================
# 검색 모드
# ============================================================================
if [ -n "$SEARCH_TERM" ]; then
    log_info "검색어: $SEARCH_TERM"
    $VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cursor = conn.execute('''
    SELECT id, filename, date, drafter
    FROM documents
    WHERE filename LIKE ? OR text_preview LIKE ?
    LIMIT 10
''', (f'%$SEARCH_TERM%', f'%$SEARCH_TERM%'))
results = cursor.fetchall()
if not results:
    print('검색 결과가 없습니다.')
else:
    print(f'{'ID':>5} | {'날짜':^12} | {'작성자':^8} | 파일명')
    print('-' * 80)
    for row in results:
        id, fn, date, drafter = row
        date = date or '-'
        drafter = drafter or '-'
        print(f'{id:>5} | {date:^12} | {drafter:^8} | {fn}')
conn.close()
"
    echo ""
    read -p "삭제할 문서의 ID를 입력하세요 (취소: 엔터): " DOC_ID
    if [ -z "$DOC_ID" ]; then
        log_info "취소되었습니다."
        exit 0
    fi
fi

# ============================================================================
# 삭제 대상 확인
# ============================================================================
if [ -z "$FILENAME" ] && [ -z "$DOC_ID" ]; then
    show_usage
    exit 1
fi

# 파일명 또는 ID로 문서 정보 조회
DOC_INFO=$($VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')

if '$DOC_ID':
    cursor = conn.execute('SELECT id, filename, date, drafter FROM documents WHERE id = ?', ('$DOC_ID',))
elif '$FILENAME':
    cursor = conn.execute('SELECT id, filename, date, drafter FROM documents WHERE filename = ?', ('$FILENAME',))

row = cursor.fetchone()
if row:
    print(f'{row[0]}|{row[1]}|{row[2] or \"-\"}|{row[3] or \"-\"}')
else:
    print('')
conn.close()
")

if [ -z "$DOC_INFO" ]; then
    log_error "문서를 찾을 수 없습니다."
    exit 1
fi

IFS='|' read -r DOC_ID FILENAME DATE DRAFTER <<< "$DOC_INFO"

echo ""
log_info "삭제 대상 문서:"
echo "  ID: $DOC_ID"
echo "  파일명: $FILENAME"
echo "  날짜: $DATE"
echo "  작성자: $DRAFTER"
echo ""

# ============================================================================
# 사용자 확인
# ============================================================================
if [ "$FORCE" = false ]; then
    read -p "정말 삭제하시겠습니까? (y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "취소되었습니다."
        exit 0
    fi
fi

# ============================================================================
# 백업 (기본값)
# ============================================================================
if [ "$NO_BACKUP" = false ]; then
    mkdir -p "$QUARANTINE_DIR"

    # PDF 파일 찾기 및 백업
    PDF_PATH=$(find docs/year_* -name "$FILENAME" 2>/dev/null | head -1)
    if [ -n "$PDF_PATH" ] && [ -f "$PDF_PATH" ]; then
        log_info "백업: $PDF_PATH → $QUARANTINE_DIR/"
        mv "$PDF_PATH" "$QUARANTINE_DIR/"
    fi

    # 텍스트 파일 백업
    TXT_FILENAME="${FILENAME%.pdf}.txt"
    TXT_FILENAME="${TXT_FILENAME%.PDF}.txt"
    TXT_PATH="$EXTRACTED_DIR/$TXT_FILENAME"
    if [ -f "$TXT_PATH" ]; then
        log_info "백업: $TXT_PATH → $QUARANTINE_DIR/"
        mv "$TXT_PATH" "$QUARANTINE_DIR/"
    fi
else
    # 완전 삭제
    PDF_PATH=$(find docs/year_* -name "$FILENAME" 2>/dev/null | head -1)
    if [ -n "$PDF_PATH" ] && [ -f "$PDF_PATH" ]; then
        log_warn "삭제: $PDF_PATH"
        rm -f "$PDF_PATH"
    fi

    TXT_FILENAME="${FILENAME%.pdf}.txt"
    TXT_FILENAME="${TXT_FILENAME%.PDF}.txt"
    TXT_PATH="$EXTRACTED_DIR/$TXT_FILENAME"
    if [ -f "$TXT_PATH" ]; then
        log_warn "삭제: $TXT_PATH"
        rm -f "$TXT_PATH"
    fi
fi

# ============================================================================
# metadata.db에서 삭제
# ============================================================================
log_info "metadata.db에서 삭제..."
$VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
conn.execute('DELETE FROM documents WHERE id = ?', ($DOC_ID,))
conn.commit()
print(f'삭제 완료: ID {$DOC_ID}')
conn.close()
"

# ============================================================================
# BM25 인덱스 재생성
# ============================================================================
echo ""
log_info "BM25 인덱스 재생성 중..."
$VENV_PYTHON scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index

# ============================================================================
# 결과
# ============================================================================
echo ""
log_success "문서 삭제 완료!"

if [ "$NO_BACKUP" = false ]; then
    log_info "백업 위치: $QUARANTINE_DIR/"
    log_info "복구하려면 파일을 docs/incoming/로 이동 후 add_docs.sh 실행"
fi

# 현재 문서 수 확인
TOTAL_DOCS=$($VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
count = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
print(count)
conn.close()
")

log_info "현재 총 문서 수: ${TOTAL_DOCS}개"
