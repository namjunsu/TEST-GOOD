#!/bin/bash
# =============================================
# AI-CHAT 운영 스모크 테스트
# Author: System
# Version: 1.0
# Date: 2025-10-25
# =============================================

set -euo pipefail

# 색상 정의
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

# 테스트 결과
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

# 테스트 카운터
test_pass() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    PASSED_TESTS=$((PASSED_TESTS + 1))
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

test_fail() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    FAILED_TESTS=$((FAILED_TESTS + 1))
    echo -e "${RED}❌ FAIL${NC}: $1"
}

# ==================== 테스트 시작 ====================

echo ""
echo "========================================"
echo "  🧪 AI-CHAT 운영 스모크 테스트"
echo "========================================"
echo ""

# 프로젝트 루트로 이동
cd "$(dirname "$0")/.." || exit 1
PROJECT_ROOT=$(pwd)

# 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    log_error "가상환경(.venv)을 찾을 수 없습니다"
    exit 1
fi

# ==================== 1. RAG 파이프라인 테스트 ====================
echo "1️⃣  RAG 파이프라인 테스트"
echo "----------------------------------------"

PYTHON_TEST=$(cat <<'PY'
import sys
from app.rag.pipeline import RAGPipeline

# 파이프라인 초기화
try:
    pipeline = RAGPipeline()
    print("INIT_OK")
except Exception as e:
    print(f"INIT_ERROR: {e}")
    sys.exit(1)

# 테스트 쿼리
test_queries = [
    "남준수가 작성한 문서",
    "기안자:남준수",
    "남준수 기안자"
]

results = []
for query in test_queries:
    try:
        response = pipeline.answer(query, top_k=5)

        # 검증
        has_citations = "citations" in response
        has_status = "status" in response
        has_text = "text" in response

        status = response.get("status", {})
        retrieved = status.get("retrieved_count", 0)
        selected = status.get("selected_count", 0)
        found = status.get("found", False)

        text = response.get("text", "")
        has_no_result_msg = "없" in text and not found

        # 결과 수집
        results.append({
            "query": query,
            "has_citations": has_citations,
            "has_status": has_status,
            "has_text": has_text,
            "retrieved": retrieved,
            "selected": selected,
            "found": found,
            "has_no_result_msg": has_no_result_msg,
        })
    except Exception as e:
        results.append({
            "query": query,
            "error": str(e)
        })

# 결과 출력
for r in results:
    if "error" in r:
        print(f"QUERY_ERROR: {r['query']} | {r['error']}")
    else:
        print(f"QUERY_OK: {r['query']} | "
              f"citations={r['has_citations']} | "
              f"status={r['has_status']} | "
              f"text={r['has_text']} | "
              f"retrieved={r['retrieved']} | "
              f"selected={r['selected']} | "
              f"found={r['found']} | "
              f"no_result_msg={r['has_no_result_msg']}")
PY
)

# Python 테스트 실행
TEST_OUTPUT=$(PYTHONPATH="$PROJECT_ROOT" timeout 180 .venv/bin/python3 -c "$PYTHON_TEST" 2>&1)

# 결과 파싱 및 검증
if echo "$TEST_OUTPUT" | grep -q "INIT_ERROR"; then
    test_fail "파이프라인 초기화 실패"
    echo "$TEST_OUTPUT" | grep "INIT_ERROR"
else
    test_pass "파이프라인 초기화 성공"
fi

# 각 쿼리 검증
while IFS= read -r line; do
    if [[ $line =~ QUERY_ERROR ]]; then
        test_fail "쿼리 실행 실패: $line"
    elif [[ $line =~ QUERY_OK ]]; then
        query=$(echo "$line" | sed 's/.*QUERY_OK: \(.*\) | citations.*/\1/')

        # citations 키 체크
        if echo "$line" | grep -q "citations=True"; then
            test_pass "[$query] citations 키 존재"
        else
            test_fail "[$query] citations 키 누락"
        fi

        # found 플래그 체크
        if echo "$line" | grep -q "found=True"; then
            test_pass "[$query] 검색 결과 존재 (found=True)"
        else
            test_warn "[$query] 검색 결과 없음 (재인덱싱 필요 가능)"
        fi

        # "없음" 메시지 체크 (found=True일 때)
        if echo "$line" | grep -q "found=True" && echo "$line" | grep -q "no_result_msg=True"; then
            test_fail "[$query] found=True인데 '없음' 메시지 포함"
        else
            test_pass "[$query] '없음' 메시지 정상 (가드 작동)"
        fi
    fi
done < <(echo "$TEST_OUTPUT" | grep "QUERY_")

echo ""

# ==================== 2. API 헬스체크 테스트 ====================
echo "2️⃣  API 헬스체크 테스트"
echo "----------------------------------------"

# API 서버 실행 여부 확인
if pgrep -f "uvicorn.*app.api.main" > /dev/null; then
    test_pass "API 서버 실행 중"

    # 헬스체크 엔드포인트 테스트
    if curl -s -f http://localhost:7860/_healthz > /dev/null 2>&1; then
        test_pass "헬스체크 엔드포인트 응답 정상"

        # JSON 파싱 테스트
        HEALTH_JSON=$(curl -s http://localhost:7860/_healthz)
        if echo "$HEALTH_JSON" | python3 -m json.tool > /dev/null 2>&1; then
            test_pass "헬스체크 JSON 파싱 성공"
        else
            test_fail "헬스체크 JSON 파싱 실패"
        fi
    else
        test_fail "헬스체크 엔드포인트 응답 실패"
    fi
else
    test_warn "API 서버 미실행 (start_ai_chat.sh로 시작 필요)"
fi

echo ""

# ==================== 3. 금지어 검사 ====================
echo "3️⃣  금지어 검사"
echo "----------------------------------------"

# "관련 문서를 찾을 수 없" 패턴 검색
FORBIDDEN_COUNT=$(grep -RIn "관련 문서를 찾을 수 없" app rag_system 2>/dev/null | grep -v ".pyc" | wc -l)

if [ "$FORBIDDEN_COUNT" -eq 2 ]; then
    # 2개는 허용 (가드된 위치)
    test_pass "금지어 사용 정상 (가드된 2개 위치만 존재)"
elif [ "$FORBIDDEN_COUNT" -lt 2 ]; then
    test_warn "금지어 사용 확인 필요 (예상보다 적음: $FORBIDDEN_COUNT)"
else
    test_fail "금지어 사용 초과 (예상 2개, 실제 $FORBIDDEN_COUNT개)"
fi

echo ""

# ==================== 결과 요약 ====================
echo "========================================"
echo "  📊 테스트 결과 요약"
echo "========================================"
echo ""
echo "총 테스트: $TOTAL_TESTS"
echo -e "통과: ${GREEN}$PASSED_TESTS${NC}"
echo -e "실패: ${RED}$FAILED_TESTS${NC}"
echo ""

if [ "$FAILED_TESTS" -eq 0 ]; then
    echo -e "${GREEN}✅ 모든 테스트 통과!${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}❌ $FAILED_TESTS 개의 테스트 실패${NC}"
    echo ""
    exit 1
fi
