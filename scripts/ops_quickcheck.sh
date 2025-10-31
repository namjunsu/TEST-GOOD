#!/bin/bash
# 5분 무결성 점검 스크립트 (ops_quickcheck.sh)
#
# 목적: 운영 환경 기본 헬스체크 (< 5분 소요)
# 사용법: bash scripts/ops_quickcheck.sh

# Note: Not using set -e to allow all checks to run even if some fail
set -o pipefail  # 파이프 오류 감지

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 결과 카운터
PASS=0
FAIL=0
WARN=0

# 헬퍼 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN++))
}

# 타임스탬프
START_TIME=$(date +%s)

echo "================================================================================"
echo "🔍 AI-CHAT 5분 무결성 점검 시작"
echo "시작 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================================"
echo ""

# =============================================================================
# 점검 1: text_preview 금지 규칙 검증 (snippet 용도는 허용)
# =============================================================================
log_info "점검 1: Retriever 코드에서 text_preview 검색 사용 금지 검증 중..."

# app/rag/retrievers/ 디렉토리에서 text_preview 사용 검색
# snippet 생성용은 허용, 검색용은 금지
TEXT_PREVIEW_COUNT=$(grep -rn "text_preview" app/rag/retrievers/ 2>/dev/null | grep -v "# " | grep -v "snippet" | grep -v "data/extracted" | wc -l || echo "0")

if [ "$TEXT_PREVIEW_COUNT" -eq 0 ]; then
    log_pass "Retriever 코드에서 text_preview 검색 사용 없음 (snippet 용도만 허용)"
else
    log_warn "Retriever 코드에서 text_preview 사용 ${TEXT_PREVIEW_COUNT}건 발견 (snippet 외 용도)"
    echo "→ 검토 필요: exact_match.py 등에서 metadata 용도로 사용 중"
fi

# =============================================================================
# 점검 2: 코드 쿼리 벤치마크 (PASS≥30)
# =============================================================================
log_info "점검 2: 코드 쿼리 벤치마크 실행 중 (목표: PASS≥30)..."

# 벤치마크 스크립트 존재 여부 확인
if [ ! -f "scripts/validate_codes.py" ]; then
    log_warn "벤치마크 스크립트 없음: scripts/validate_codes.py"
else
    # 벤치마크 실행 (타임아웃 60초)
    BENCHMARK_OUTPUT=$(timeout 60 .venv/bin/python3 scripts/validate_codes.py 2>&1 || true)

    # PASS 카운트 추출 (예: "PASS: 35/50")
    PASS_COUNT=$(echo "$BENCHMARK_OUTPUT" | grep -oP 'PASS:\s*\K\d+' | head -1 || echo "0")

    if [ "$PASS_COUNT" -ge 30 ]; then
        log_pass "코드 쿼리 벤치마크 통과: PASS=$PASS_COUNT (≥30)"
    else
        log_fail "코드 쿼리 벤치마크 실패: PASS=$PASS_COUNT (<30)"
        echo "→ 벤치마크 출력:"
        echo "$BENCHMARK_OUTPUT" | tail -20
    fi
fi

# =============================================================================
# 점검 3: 메트릭스 엔드포인트 검증 (stale_index_entries == 0)
# =============================================================================
log_info "점검 3: 메트릭스 엔드포인트 검증 중 (stale_index_entries == 0)..."

# 메트릭스 엔드포인트 호출 (타임아웃 5초)
METRICS_RESPONSE=$(timeout 5 curl -s http://127.0.0.1:7860/metrics 2>/dev/null || echo "{}")

# stale_index_entries 추출 (jq 사용 또는 grep)
if command -v jq &> /dev/null; then
    STALE_ENTRIES=$(echo "$METRICS_RESPONSE" | jq -r '.stale_index_entries // "N/A"' 2>/dev/null || echo "N/A")
else
    # jq 없으면 grep 사용
    STALE_ENTRIES=$(echo "$METRICS_RESPONSE" | grep -oP '"stale_index_entries":\s*\K\d+' || echo "N/A")
fi

if [ "$STALE_ENTRIES" = "0" ]; then
    log_pass "인덱스 동기화 상태 정상: stale_index_entries=0"
elif [ "$STALE_ENTRIES" = "N/A" ]; then
    log_warn "메트릭스 엔드포인트 응답 없음 (서버 미실행?)"
else
    log_fail "인덱스 비동기 상태 감지: stale_index_entries=$STALE_ENTRIES"
    echo "→ 수정 필요: .venv/bin/python3 scripts/reindex_atomic.py 실행"
fi

# =============================================================================
# 점검 4: 데이터베이스 무결성 (기본)
# =============================================================================
log_info "점검 4: 데이터베이스 무결성 검증 중..."

# metadata.db 존재 확인
if [ ! -f "metadata.db" ]; then
    log_fail "metadata.db 파일 없음"
else
    # WAL 파일 크기 확인 (너무 크면 VACUUM 필요)
    if [ -f "metadata.db-wal" ]; then
        WAL_SIZE=$(stat -f%z "metadata.db-wal" 2>/dev/null || stat -c%s "metadata.db-wal" 2>/dev/null || echo "0")
        WAL_SIZE_MB=$((WAL_SIZE / 1024 / 1024))

        if [ "$WAL_SIZE_MB" -gt 100 ]; then
            log_warn "WAL 파일 크기: ${WAL_SIZE_MB}MB (>100MB, VACUUM 권장)"
        else
            log_pass "데이터베이스 상태 정상 (WAL=${WAL_SIZE_MB}MB)"
        fi
    else
        log_pass "데이터베이스 상태 정상 (WAL 없음)"
    fi
fi

# =============================================================================
# 점검 5: 디스크 공간 확인
# =============================================================================
log_info "점검 5: 디스크 공간 확인 중..."

# data/extracted 디렉토리 크기
EXTRACTED_SIZE=$(du -sh data/extracted 2>/dev/null | awk '{print $1}' || echo "N/A")

# docs/incoming 파일 개수
INCOMING_COUNT=$(find docs/incoming -type f -name "*.pdf" 2>/dev/null | wc -l || echo "0")

# 루트 디렉토리 디스크 사용률
DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | tr -d '%')

if [ "$DISK_USAGE" -lt 80 ]; then
    log_pass "디스크 공간 충분: ${DISK_USAGE}% 사용 (data/extracted=${EXTRACTED_SIZE}, incoming=${INCOMING_COUNT}개)"
elif [ "$DISK_USAGE" -lt 90 ]; then
    log_warn "디스크 공간 부족 경고: ${DISK_USAGE}% 사용"
else
    log_fail "디스크 공간 위험: ${DISK_USAGE}% 사용 (>90%)"
fi

# =============================================================================
# 점검 6: 최근 로그 오류 검색
# =============================================================================
log_info "점검 6: 최근 로그 오류 검색 중 (최근 10분)..."

# 최근 로그 파일 찾기
RECENT_LOGS=$(find logs -name "*.log" -mmin -10 2>/dev/null || true)

if [ -z "$RECENT_LOGS" ]; then
    log_warn "최근 10분 내 로그 파일 없음"
else
    # ERROR 라인 카운트 (newline 제거)
    ERROR_COUNT=$(grep -h "ERROR" $RECENT_LOGS 2>/dev/null | wc -l | tr -d ' \n' || echo "0")

    if [ "$ERROR_COUNT" -eq 0 ]; then
        log_pass "최근 로그에 오류 없음"
    elif [ "$ERROR_COUNT" -lt 5 ]; then
        log_warn "최근 로그에 오류 ${ERROR_COUNT}건 발견 (<5건)"
    else
        log_fail "최근 로그에 오류 ${ERROR_COUNT}건 발견 (≥5건)"
        echo "→ 최근 오류 샘플:"
        grep -h "ERROR" $RECENT_LOGS 2>/dev/null | tail -3 || true
    fi
fi

# =============================================================================
# 최종 결과 요약
# =============================================================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "================================================================================"
echo "📊 점검 결과 요약"
echo "================================================================================"
echo -e "${GREEN}PASS:${NC} $PASS"
echo -e "${RED}FAIL:${NC} $FAIL"
echo -e "${YELLOW}WARN:${NC} $WARN"
echo ""
echo "소요 시간: ${DURATION}초"
echo "종료 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================================"

# 종료 코드 결정 (FAIL이 0이면 성공)
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ 무결성 점검 통과${NC}"
    exit 0
else
    echo -e "${RED}❌ 무결성 점검 실패 (FAIL=$FAIL)${NC}"
    exit 1
fi
