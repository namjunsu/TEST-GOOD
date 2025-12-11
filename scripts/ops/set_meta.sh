#!/usr/bin/env bash
# ============================================================================
# 메타데이터 수정 스크립트
# ============================================================================
# 사용법:
#   ./scripts/ops/set_meta.sh --id 123 --date 2024-01-15
#   ./scripts/ops/set_meta.sh --id 123 --drafter 하승범
#   ./scripts/ops/set_meta.sh --id 123 --category proposal
#   ./scripts/ops/set_meta.sh "파일명.pdf" --date 2024-01-15 --drafter 하승범
#   ./scripts/ops/set_meta.sh --reparse 123  # 텍스트에서 메타데이터 재추출
#
# 설명:
#   특정 문서의 메타데이터를 수동으로 수정합니다.
#   검토서, 보고서 등 자동 추출이 어려운 문서에 유용합니다.
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

log_info() { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error() { echo -e "${RED}❌ $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }

show_usage() {
    echo "사용법:"
    echo "  $0 --id 123 --date 2024-01-15         # 날짜 수정"
    echo "  $0 --id 123 --drafter 하승범           # 작성자 수정"
    echo "  $0 --id 123 --category proposal       # 카테고리 수정"
    echo "  $0 \"파일명.pdf\" --date 2024-01-15     # 파일명으로 지정"
    echo "  $0 --reparse 123                      # 텍스트에서 재추출"
    echo "  $0 --reparse-all                      # 전체 문서 재추출"
    echo ""
    echo "카테고리 옵션:"
    echo "  proposal  - 기안서"
    echo "  review    - 검토서"
    echo "  report    - 보고서"
    echo "  minutes   - 회의록"
    echo "  disposal  - 폐기/불용"
    echo "  other     - 기타"
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
DOC_ID=""
FILENAME=""
NEW_DATE=""
NEW_DRAFTER=""
NEW_CATEGORY=""
REPARSE_ID=""
REPARSE_ALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --id)
            DOC_ID="$2"
            shift 2
            ;;
        --date)
            NEW_DATE="$2"
            shift 2
            ;;
        --drafter)
            NEW_DRAFTER="$2"
            shift 2
            ;;
        --category)
            NEW_CATEGORY="$2"
            shift 2
            ;;
        --reparse)
            REPARSE_ID="$2"
            shift 2
            ;;
        --reparse-all)
            REPARSE_ALL=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            if [[ "$1" == *.pdf || "$1" == *.PDF ]]; then
                FILENAME="$1"
            else
                echo "알 수 없는 옵션: $1"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# ============================================================================
# 전체 재파싱 모드
# ============================================================================
if [ "$REPARSE_ALL" = true ]; then
    log_info "전체 문서 메타데이터 재파싱..."
    $VENV_PYTHON scripts/ops/reparse_metadata.py
    exit $?
fi

# ============================================================================
# 단일 문서 재파싱 모드
# ============================================================================
if [ -n "$REPARSE_ID" ]; then
    log_info "문서 ID $REPARSE_ID 재파싱..."
    $VENV_PYTHON scripts/ops/reparse_metadata.py --limit 1 --force <<< "$REPARSE_ID"

    # 결과 확인
    $VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cursor = conn.execute('SELECT filename, date, drafter FROM documents WHERE id = ?', ($REPARSE_ID,))
row = cursor.fetchone()
if row:
    print(f'파일명: {row[0]}')
    print(f'날짜: {row[1] or \"(없음)\"}')
    print(f'작성자: {row[2] or \"(없음)\"}')
conn.close()
"
    exit 0
fi

# ============================================================================
# 대상 문서 확인
# ============================================================================
if [ -z "$DOC_ID" ] && [ -z "$FILENAME" ]; then
    show_usage
    exit 1
fi

# 파일명으로 ID 조회
if [ -n "$FILENAME" ] && [ -z "$DOC_ID" ]; then
    DOC_ID=$($VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cursor = conn.execute('SELECT id FROM documents WHERE filename = ?', ('$FILENAME',))
row = cursor.fetchone()
print(row[0] if row else '')
conn.close()
")
fi

if [ -z "$DOC_ID" ]; then
    log_error "문서를 찾을 수 없습니다: $FILENAME"
    exit 1
fi

# 현재 정보 표시
log_info "현재 문서 정보:"
$VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cursor = conn.execute('''
    SELECT id, filename, date, drafter, category
    FROM documents WHERE id = ?
''', ($DOC_ID,))
row = cursor.fetchone()
if row:
    print(f'  ID: {row[0]}')
    print(f'  파일명: {row[1]}')
    print(f'  날짜: {row[2] or \"(없음)\"}')
    print(f'  작성자: {row[3] or \"(없음)\"}')
    print(f'  카테고리: {row[4] or \"(없음)\"}')
conn.close()
"

# ============================================================================
# 수정할 항목이 없으면 종료
# ============================================================================
if [ -z "$NEW_DATE" ] && [ -z "$NEW_DRAFTER" ] && [ -z "$NEW_CATEGORY" ]; then
    echo ""
    log_warn "수정할 항목을 지정하세요 (--date, --drafter, --category)"
    exit 0
fi

# ============================================================================
# 메타데이터 업데이트
# ============================================================================
echo ""
log_info "메타데이터 업데이트 중..."

$VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')

updates = []
params = []

new_date = '$NEW_DATE'
new_drafter = '$NEW_DRAFTER'
new_category = '$NEW_CATEGORY'

if new_date:
    updates.append('date = ?')
    params.append(new_date)
    # year, month도 업데이트
    if len(new_date) >= 7:
        updates.append('year = ?')
        params.append(new_date[:4])
        updates.append('month = ?')
        params.append(new_date[:7])
    print(f'날짜: → {new_date}')

if new_drafter:
    updates.append('drafter = ?')
    params.append(new_drafter)
    print(f'작성자: → {new_drafter}')

if new_category:
    updates.append('category = ?')
    params.append(new_category)
    print(f'카테고리: → {new_category}')

if updates:
    params.append($DOC_ID)
    sql = f'UPDATE documents SET {', '.join(updates)} WHERE id = ?'
    conn.execute(sql, params)
    conn.commit()

conn.close()
"

log_success "업데이트 완료!"

# ============================================================================
# 인덱스 재생성 여부 확인
# ============================================================================
echo ""
read -p "BM25 인덱스를 재생성하시겠습니까? (y/N): " REINDEX
if [[ "$REINDEX" =~ ^[Yy]$ ]]; then
    log_info "인덱스 재생성 중..."
    $VENV_PYTHON scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index
    log_success "인덱스 재생성 완료!"
else
    log_info "인덱스 재생성을 건너뜁니다."
    log_info "나중에 ./scripts/core/reindex_atomic.py를 실행하세요."
fi
