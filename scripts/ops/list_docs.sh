#!/usr/bin/env bash
# ============================================================================
# 문서 목록 조회 스크립트
# ============================================================================
# 사용법:
#   ./scripts/ops/list_docs.sh                    # 전체 목록 (최근 50개)
#   ./scripts/ops/list_docs.sh --year 2024        # 2024년 문서만
#   ./scripts/ops/list_docs.sh --drafter 하승범    # 작성자 필터
#   ./scripts/ops/list_docs.sh --search "UPS"     # 키워드 검색
#   ./scripts/ops/list_docs.sh --stats            # 통계 보기
#   ./scripts/ops/list_docs.sh --missing          # 메타데이터 누락 문서
# ============================================================================

set -Eeuo pipefail

# 색상
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 경로
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

VENV_PYTHON=".venv/bin/python3"

# ============================================================================
# 가상환경 확인
# ============================================================================
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ 가상환경이 없습니다."
    exit 1
fi

# ============================================================================
# 인자 파싱
# ============================================================================
YEAR=""
DRAFTER=""
SEARCH=""
STATS_MODE=false
MISSING_MODE=false
LIMIT=50
ALL_MODE=false

show_usage() {
    echo "사용법:"
    echo "  $0                        # 전체 목록 (최근 50개)"
    echo "  $0 --all                  # 전체 목록 (제한 없음)"
    echo "  $0 --year 2024            # 연도 필터"
    echo "  $0 --drafter 하승범        # 작성자 필터"
    echo "  $0 --search \"검색어\"      # 파일명/내용 검색"
    echo "  $0 --stats                # 통계 보기"
    echo "  $0 --missing              # 메타데이터 누락 문서"
    echo "  $0 --limit 100            # 출력 개수 제한"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --year)
            YEAR="$2"
            shift 2
            ;;
        --drafter)
            DRAFTER="$2"
            shift 2
            ;;
        --search)
            SEARCH="$2"
            shift 2
            ;;
        --stats)
            STATS_MODE=true
            shift
            ;;
        --missing)
            MISSING_MODE=true
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --all)
            ALL_MODE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            show_usage
            exit 1
            ;;
    esac
done

# ============================================================================
# 통계 모드
# ============================================================================
if [ "$STATS_MODE" = true ]; then
    echo -e "${BLUE}📊 문서 통계${NC}"
    echo "=============================================="
    $VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')

# 총 문서 수
total = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
print(f'총 문서 수: {total}개')
print()

# 연도별 분포
print('📅 연도별 분포:')
cursor = conn.execute('''
    SELECT year, COUNT(*) as cnt
    FROM documents
    WHERE year IS NOT NULL AND year != ''
    GROUP BY year
    ORDER BY year
''')
for row in cursor:
    print(f'  {row[0]}: {row[1]}개')

# 연도 정보 없음
no_year = conn.execute('''
    SELECT COUNT(*) FROM documents
    WHERE year IS NULL OR year = ''
''').fetchone()[0]
if no_year > 0:
    print(f'  (연도 없음): {no_year}개')

print()

# 작성자별 분포 (상위 10명)
print('👤 작성자별 분포 (상위 10명):')
cursor = conn.execute('''
    SELECT drafter, COUNT(*) as cnt
    FROM documents
    WHERE drafter IS NOT NULL AND drafter != '' AND drafter != '정보 없음'
    GROUP BY drafter
    ORDER BY cnt DESC
    LIMIT 10
''')
for row in cursor:
    print(f'  {row[0]}: {row[1]}개')

# 작성자 정보 없음
no_drafter = conn.execute('''
    SELECT COUNT(*) FROM documents
    WHERE drafter IS NULL OR drafter = '' OR drafter = '정보 없음'
''').fetchone()[0]
print(f'  (작성자 없음): {no_drafter}개')

print()

# 카테고리별 분포
print('📁 카테고리별 분포:')
cursor = conn.execute('''
    SELECT category, COUNT(*) as cnt
    FROM documents
    GROUP BY category
    ORDER BY cnt DESC
''')
for row in cursor:
    cat = row[0] or '(없음)'
    print(f'  {cat}: {row[1]}개')

conn.close()
"
    exit 0
fi

# ============================================================================
# 누락 문서 모드
# ============================================================================
if [ "$MISSING_MODE" = true ]; then
    echo -e "${YELLOW}⚠️  메타데이터 누락 문서${NC}"
    echo "=============================================="
    $VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')

# 날짜 누락
print('📅 날짜 누락:')
cursor = conn.execute('''
    SELECT id, filename FROM documents
    WHERE date IS NULL OR date = '' OR date = '정보 없음'
''')
for row in cursor:
    print(f'  [{row[0]}] {row[1]}')

print()

# 작성자 누락
print('👤 작성자 누락:')
cursor = conn.execute('''
    SELECT id, filename FROM documents
    WHERE drafter IS NULL OR drafter = '' OR drafter = '정보 없음'
''')
for row in cursor:
    print(f'  [{row[0]}] {row[1]}')

conn.close()
"
    exit 0
fi

# ============================================================================
# 목록 조회
# ============================================================================
LIMIT_CLAUSE=""
if [ "$ALL_MODE" = false ]; then
    LIMIT_CLAUSE="LIMIT $LIMIT"
fi

$VENV_PYTHON -c "
import sqlite3
conn = sqlite3.connect('metadata.db')

# 쿼리 조건 생성
conditions = []
params = []

year = '$YEAR'
drafter = '$DRAFTER'
search = '$SEARCH'

if year:
    conditions.append('year = ?')
    params.append(year)

if drafter:
    conditions.append('drafter = ?')
    params.append(drafter)

if search:
    conditions.append('(filename LIKE ? OR text_preview LIKE ?)')
    params.extend([f'%{search}%', f'%{search}%'])

where_clause = ''
if conditions:
    where_clause = 'WHERE ' + ' AND '.join(conditions)

query = f'''
    SELECT id, filename, date, drafter, category
    FROM documents
    {where_clause}
    ORDER BY date DESC, id DESC
    $LIMIT_CLAUSE
'''

cursor = conn.execute(query, params)
results = cursor.fetchall()

if not results:
    print('조건에 맞는 문서가 없습니다.')
else:
    print(f'{'ID':>5} | {'날짜':^12} | {'작성자':^8} | {'카테고리':^10} | 파일명')
    print('-' * 100)
    for row in results:
        id, fn, date, drafter, cat = row
        date = date or '-'
        drafter = drafter or '-'
        cat = cat or '-'
        # 파일명이 너무 길면 자르기
        if len(fn) > 50:
            fn = fn[:47] + '...'
        print(f'{id:>5} | {date:^12} | {drafter:^8} | {cat:^10} | {fn}')

total = conn.execute(f'SELECT COUNT(*) FROM documents {where_clause}', params).fetchone()[0]
print()
print(f'총 {total}개 문서 중 {len(results)}개 표시')
conn.close()
"
