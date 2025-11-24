#!/bin/bash
# 메타데이터 검증 크론잡 설정 스크립트

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PATH="${PROJECT_DIR}/.venv"
LOG_DIR="${PROJECT_DIR}/logs/cron"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

echo "=============================================="
echo "📅 AI-CHAT 메타데이터 검증 크론잡 설정"
echo "=============================================="
echo ""
echo "프로젝트 경로: $PROJECT_DIR"
echo "가상환경: $VENV_PATH"
echo "로그 경로: $LOG_DIR"
echo ""

# 크론잡 래퍼 스크립트 생성
cat > "${PROJECT_DIR}/scripts/cron_wrapper.sh" << 'EOF'
#!/bin/bash
# 크론잡 실행 래퍼

PROJECT_DIR="/home/wnstn4647/AI-CHAT"
VENV_PATH="${PROJECT_DIR}/.venv"
LOG_DIR="${PROJECT_DIR}/logs/cron"

# 환경 변수 설정
export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH}"
export PATH="${VENV_PATH}/bin:${PATH}"

# 가상환경 활성화
source "${VENV_PATH}/bin/activate"

# 작업 디렉토리 변경
cd "$PROJECT_DIR"

# 실행할 스크립트 선택
case "$1" in
    daily)
        # 일일 검증 (매일 오전 2시)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 일일 메타데이터 검증 시작" >> "${LOG_DIR}/daily.log"
        python scripts/validate_metadata.py >> "${LOG_DIR}/daily.log" 2>&1

        # 결과 요약 추출
        if [ -f "reports/metadata/latest.json" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 검증 완료" >> "${LOG_DIR}/daily.log"
            python -c "
import json
with open('reports/metadata/latest.json') as f:
    data = json.load(f)
    summary = data['summary']
    recs = len(data.get('recommendations', []))
    print(f'  - 전체: {summary.get(\"total_documents\", 0)}개')
    print(f'  - 문제: {summary.get(\"missing_drafters\", 0)}개')
    print(f'  - 권장사항: {recs}개')
" >> "${LOG_DIR}/daily.log"
        fi
        ;;

    weekly)
        # 주간 복구 시도 (매주 일요일 오전 3시)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 주간 메타데이터 복구 시작" >> "${LOG_DIR}/weekly.log"

        # 기안자 복구
        echo "y" | python scripts/fix_missing_drafters.py >> "${LOG_DIR}/weekly.log" 2>&1

        # 카테고리 재분류
        python scripts/auto_categorize_documents.py >> "${LOG_DIR}/weekly.log" 2>&1

        # 인덱스 재생성 (필요시)
        python scripts/validate_metadata.py | grep "불일치" && \
            python scripts/reindex_atomic.py >> "${LOG_DIR}/weekly.log" 2>&1

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 주간 복구 완료" >> "${LOG_DIR}/weekly.log"
        ;;

    monthly)
        # 월간 정밀 분석 (매월 1일 오전 4시)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 월간 정밀 분석 시작" >> "${LOG_DIR}/monthly.log"

        # 실패 패턴 분석
        python scripts/analyze_failed_extractions.py > "reports/failed_patterns_$(date +%Y%m).txt" 2>&1

        # 전체 재인덱싱
        python scripts/reindex_atomic.py >> "${LOG_DIR}/monthly.log" 2>&1

        # 상세 보고서 생성
        python scripts/validate_metadata.py >> "${LOG_DIR}/monthly.log" 2>&1

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 월간 분석 완료" >> "${LOG_DIR}/monthly.log"
        ;;

    *)
        echo "Usage: $0 {daily|weekly|monthly}"
        exit 1
        ;;
esac
EOF

chmod +x "${PROJECT_DIR}/scripts/cron_wrapper.sh"

# 크론탭 항목 생성
CRON_ENTRIES=$(cat << EOF

# AI-CHAT 메타데이터 자동 검증
# 일일 검증 (매일 오전 2시)
0 2 * * * ${PROJECT_DIR}/scripts/cron_wrapper.sh daily

# 주간 복구 (매주 일요일 오전 3시)
0 3 * * 0 ${PROJECT_DIR}/scripts/cron_wrapper.sh weekly

# 월간 분석 (매월 1일 오전 4시)
0 4 1 * * ${PROJECT_DIR}/scripts/cron_wrapper.sh monthly

# 로그 순환 (매일 오전 5시, 30일 이상 된 로그 삭제)
0 5 * * * find ${LOG_DIR} -name "*.log" -mtime +30 -delete

EOF
)

echo "다음 크론잡을 추가합니다:"
echo "=============================================="
echo "$CRON_ENTRIES"
echo "=============================================="
echo ""

# 사용자 확인
read -p "크론탭에 추가하시겠습니까? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 현재 크론탭 백업
    crontab -l > "${PROJECT_DIR}/crontab_backup_$(date +%Y%m%d_%H%M%S).txt" 2>/dev/null || true

    # 새 크론잡 추가 (중복 방지)
    (crontab -l 2>/dev/null | grep -v "AI-CHAT 메타데이터"; echo "$CRON_ENTRIES") | crontab -

    echo "✅ 크론잡이 추가되었습니다."
    echo ""
    echo "확인: crontab -l"
    echo "로그 확인: tail -f ${LOG_DIR}/daily.log"
else
    echo "❌ 취소되었습니다."
    echo ""
    echo "수동으로 크론잡을 추가하려면:"
    echo "  1. crontab -e"
    echo "  2. 위의 내용을 붙여넣기"
fi

echo ""
echo "=============================================="
echo "📋 수동 실행 명령어:"
echo "=============================================="
echo "일일 검증: ${PROJECT_DIR}/scripts/cron_wrapper.sh daily"
echo "주간 복구: ${PROJECT_DIR}/scripts/cron_wrapper.sh weekly"
echo "월간 분석: ${PROJECT_DIR}/scripts/cron_wrapper.sh monthly"
echo ""
echo "로그 위치: ${LOG_DIR}/"
echo "  - daily.log   : 일일 검증 로그"
echo "  - weekly.log  : 주간 복구 로그"
echo "  - monthly.log : 월간 분석 로그"
echo ""