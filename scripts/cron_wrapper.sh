#!/bin/bash
# 크론잡 실행 래퍼

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
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
