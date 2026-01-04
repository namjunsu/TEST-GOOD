# Phase 3.2 Critical Bug Fix Report

## 📅 발견 및 수정일
2026-01-04 23:37

## 🚨 버그 심각도
**CRITICAL** - 사용자가 에러 메시지를 받는 직접적인 원인

## 📋 증상

### 사용자 보고
```
👤 최새름 문서 찾아줘
🤖 오류가 발생했다. 잠시 후 다시 시도하라.
```

### 로그 분석
```json
{
  "query": "최새름 문서 찾아줘",
  "answer": "[E_GENERATE] 현재 생성기가 비활성 상태입니다.",
  "success": true,  // ❌ 잘못된 판정!
  "error_type": null,
  "search_results_count": 3,
  "mode": "qa"
}
```

**문제**: 에러 메시지 `[E_GENERATE]`가 포함된 답변을 **success=true**로 잘못 판정

## 🔍 근본 원인 분석

### 1차 원인: GPU 메모리 부족
```
CUDA out of memory. Tried to allocate 978.00 MiB.
GPU 0 has 79.19 GiB total, 495.00 MiB free.
Process 2988850 has 75.05 GiB memory in use.
```

**발생 메커니즘**:
1. 기존 Streamlit 프로세스(PID 2895463)가 vLLM 인스턴스를 보유 중
2. 해당 vLLM 프로세스(PID 2988850)가 GPU 75GB 점유
3. 새로운 쿼리 시 vLLM 초기화 시도 → GPU 메모리 부족으로 실패
4. DummyGenerator fallback 동작
5. `[E_GENERATE]` 에러 메시지 반환

### 2차 원인 (CRITICAL): ConversationService 버그

**파일**: `app/rag/services/conversation_service.py:111-130`

**기존 코드**:
```python
def _evaluate_result(self, result, mode, elapsed_ms, search_count):
    """응답 성공/실패 판정"""
    answer_text = result.get("text", "")

    # 실패 케이스 감지
    if not answer_text or answer_text.strip() == "":
        return False, "no_answer"

    if elapsed_ms > PipelineConfig.ANSWER_TIMEOUT_MS:
        return True, "timeout"

    if search_count == 0 and mode in ["search", "document"]:
        return True, "no_results"

    if answer_text.startswith("{") and "keywords" in answer_text:
        return False, "llm_hallucination"

    return True, None  # ❌ [E_GENERATE] 메시지도 여기로!
```

**문제점**:
- ✅ 빈 답변 감지
- ✅ Timeout 감지
- ✅ 검색 결과 없음 감지
- ✅ JSON 환각 감지
- ❌ **에러 메시지 패턴 감지 누락** ← Phase 3.2 리팩토링 시 놓친 케이스

## 🛠️ 해결 방법

### 1단계: ConversationService 로직 수정

**변경사항**:
```python
def _evaluate_result(self, result, mode, elapsed_ms, search_count):
    """응답 성공/실패 판정"""
    answer_text = result.get("text", "")

    # 실패 케이스 감지
    if not answer_text or answer_text.strip() == "":
        return False, "no_answer"

    # ✨ NEW: 에러 메시지 감지
    if answer_text.startswith("[E_"):
        # [E_GENERATE], [E_SEARCH], [E_MODEL] 등 에러 코드
        return False, "generator_error"

    if elapsed_ms > PipelineConfig.ANSWER_TIMEOUT_MS:
        return True, "timeout"

    if search_count == 0 and mode in ["search", "document"]:
        return True, "no_results"

    if answer_text.startswith("{") and "keywords" in answer_text:
        return False, "llm_hallucination"

    return True, None
```

**추가된 에러 타입**: `generator_error`

### 2단계: Streamlit 재시작

**문제**: Zombie 프로세스 (PID 2895463) + GPU 메모리 점유

**해결**:
```bash
kill -9 2895463                    # Zombie Streamlit 종료
# vLLM 프로세스(2988850) 자동 종료됨
# GPU 메모리: 75GB → 494MB

# 재시작
streamlit run web_interface.py --server.port 8501
```

## ✅ 검증 결과

### Unit Test
```python
from app.rag.services import ConversationService

svc = ConversationService()

# 테스트 1: 에러 메시지
result1 = {'text': '[E_GENERATE] 현재 생성기가 비활성 상태입니다.'}
success1, error1 = svc._evaluate_result(result1, 'qa', 5000, 3)
assert success1 == False  # ✅
assert error1 == 'generator_error'  # ✅

# 테스트 2: 정상 답변
result2 = {'text': '검색 결과입니다.'}
success2, error2 = svc._evaluate_result(result2, 'qa', 5000, 3)
assert success2 == True  # ✅
assert error2 is None  # ✅

# 테스트 3: 빈 답변
result3 = {'text': ''}
success3, error3 = svc._evaluate_result(result3, 'qa', 5000, 3)
assert success3 == False  # ✅
assert error3 == 'no_answer'  # ✅
```

**결과**: ✅ 모든 테스트 통과

### Integration Test

**이전**:
```json
{
  "answer": "[E_GENERATE] 현재 생성기가 비활성 상태입니다.",
  "success": true,      // ❌ 잘못된 판정
  "error_type": null
}
```

**이후**:
```json
{
  "answer": "[E_GENERATE] 현재 생성기가 비활성 상태입니다.",
  "success": false,     // ✅ 올바른 판정
  "error_type": "generator_error"
}
```

## 📊 영향 분석

### 영향 범위
- **파일**: `app/rag/services/conversation_service.py` (1개)
- **변경**: +5줄 (에러 감지 로직 추가)
- **영향 받는 모드**: 모든 모드 (QA, SEARCH, DOCUMENT, COST 등)

### 사용자 경험 개선
**이전**:
- 에러 메시지를 받아도 로그에는 성공으로 기록
- 관리자가 문제 파악 어려움
- 에러 패턴 분석 불가능

**이후**:
- 에러 메시지 정확히 감지
- `error_type=generator_error`로 분류
- 에러 통계 및 모니터링 가능

## 🔄 Git 커밋

### Commit
- **Hash**: `164c834`
- **Message**: "fix: Phase 3.2 버그 수정 - 에러 메시지 감지 누락"
- **Files**: 1 file changed, 5 insertions(+)

## 💡 교훈 (Lessons Learned)

### 1. Phase 3 리팩토링 시 놓친 엣지 케이스
**문제**:
- ConversationService 추출 시 기존 코드를 그대로 옮김
- 에러 메시지 패턴 감지 로직이 원래부터 없었음
- Phase 3.2 리팩토링 자체는 문제 없음

**개선**:
- 리팩토링 시 엣지 케이스 점검 체크리스트 필요
- 에러 메시지 패턴 테스트 케이스 추가

### 2. 에러 메시지 표준화의 중요성
**현재 패턴**:
```
[E_GENERATE]  - 생성기 에러
[E_SEARCH]    - 검색 에러
[E_MODEL]     - 모델 로딩 에러
```

**장점**:
- 정규표현식으로 감지 가능
- 에러 타입 분류 용이
- 로그 분석 편리

### 3. GPU 메모리 관리
**문제**:
- Streamlit의 `@st.cache_resource`가 vLLM 인스턴스를 재사용해야 함
- 하지만 zombie 프로세스로 인해 메모리 정리 안 됨

**해결**:
- 정기적인 프로세스 모니터링 필요
- GPU 메모리 임계값 알림 설정

## 📈 모니터링 개선 제안

### 1. 에러 타입별 통계
```sql
SELECT error_type, COUNT(*) as count
FROM conversation_logs
WHERE success = false
GROUP BY error_type
ORDER BY count DESC;
```

**예상 결과**:
```
error_type         | count
-------------------+-------
generator_error    | 15    ← NEW 타입!
no_answer          | 8
llm_hallucination  | 3
no_results         | 2
```

### 2. 실시간 알림
- `generator_error` 발생 시 관리자에게 알림
- GPU 메모리 사용률 80% 초과 시 경고
- vLLM 프로세스 비정상 종료 감지

## 🚀 다음 단계

### 즉시 조치
- [x] ConversationService 버그 수정
- [x] Streamlit 재시작
- [x] GPU 메모리 정리
- [x] Git 커밋 및 문서화

### 모니터링 (1주일)
- [ ] `generator_error` 발생 빈도 추적
- [ ] GPU 메모리 사용 패턴 분석
- [ ] Streamlit 프로세스 안정성 확인

### 장기 개선 (Phase 4 고려)
- [ ] GPU OOM 자동 복구 메커니즘
- [ ] vLLM 인스턴스 헬스체크
- [ ] 에러 메시지 표준화 및 다국어 지원

## 📚 관련 문서

- **Phase 3.1-3.2 요약**: `PHASE3_SERVICE_EXTRACTION_SUMMARY.md`
- **Phase 3 현황**: `PHASE3_STATUS.md`
- **본 버그 수정 보고서**: `PHASE3_BUGFIX_REPORT.md`

## 👥 기여자

- **버그 발견**: User (실제 쿼리 테스트)
- **분석 및 수정**: Claude Sonnet 4.5
- **검증**: Unit tests + Integration tests
- **배포**: 2026-01-04

---

**Status**: ✅ Bug Fixed & Deployed

**Severity**: CRITICAL → RESOLVED

**Root Cause**: Missing error message pattern detection in Phase 3.2 refactoring

**Resolution**: Added `[E_*` pattern detection + `generator_error` type

