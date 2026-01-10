# Document Mode Performance Profiling Analysis

## 문제 상황

- **이전 성능**: Line 6 (988초, 16.5분)
- **청크 기반 로딩 적용 후**: Line 12 (681초, 11.4분)
- **개선율**: 31% (307초 단축)
- **목표**: 3-8초 (현재 대비 85-227배 빠르게)

## 문제 진단

41KB 파일이 681초(11.4분)나 걸린다는 것은 **파일 I/O가 아닌 다른 병목**이 있다는 의미입니다.

### 가능한 병목 지점

1. **LLM 생성 시간** (가장 유력)
   - vLLM H100 백엔드로 텍스트 생성 시간
   - 긴 컨텍스트 처리 (최대 24K chars)
   - 긴 응답 생성 (최대 8192 토큰)

2. **네트워크 지연**
   - vLLM API 통신 지연
   - 요청/응답 직렬화 오버헤드

3. **컨텍스트 처리**
   - 프롬프트 빌드 시간
   - 텍스트 전처리

4. **DB/인덱스 접근**
   - 메타데이터 조회
   - BM25 인덱스 접근

## 추가된 계측 (Instrumentation)

### 1. 전체 파이프라인 타이밍 (`handle()` 메서드)

```python
timings = {
    "1_identify_document": X.XXs,
    "2_get_metadata": X.XXs,
    "3_route_query": X.XXs,
    "4_load_text": X.XXs,
    "5_generate_answer": X.XXs,  # ← 가장 중요
    "6_build_evidence": X.XXs,
    "total_time": X.XXs
}
```

**5초 이상 걸리면 자동으로 WARNING 로그 출력**:
```
⏱️ PERFORMANCE: Document mode took XXX.XXs
  - Identify: X.XXs
  - Metadata: X.XXs
  - Routing: X.XXs
  - Load Text: X.XXs
  - Generate Answer: X.XXs  # ← 주목
  - Build Evidence: X.XXs
```

### 2. LLM 생성 세부 타이밍 (`_generate_llm_answer()` 메서드)

```python
📊 LLM 설정: mode=rag, context_len=XXXX, full_text_len=XXXX,
             max_tokens=XXXX, prompt_build_time=X.XXXs

⏱️ LLM 생성 완료: XXX.XXs (응답 길이: XXXX chars)
```

## 테스트 방법

### 옵션 1: 직접 프로파일링 스크립트 실행

```bash
# 서버를 재시작할 필요 없이 직접 실행
python3 scripts/profile_document_performance.py
```

**장점**:
- 독립 실행으로 다른 요청 영향 없음
- 단계별 시간이 로그에 명확히 출력됨

**예상 출력**:
```
🔍 Document 모드 성능 프로파일링 시작
📝 쿼리: 주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘
⚙️ RAG 파이프라인 초기화 중...
🚀 쿼리 실행 중...

# ... 상세 로그들 ...

⏱️ PERFORMANCE: Document mode took 681.XXs
  - Identify: 0.XXs
  - Metadata: 0.XXs
  - Routing: 0.XXs
  - Load Text: 0.XXs
  - Generate Answer: 680.XXs  ← 이게 범인일 가능성 99%
  - Build Evidence: 0.XXs

✅ 쿼리 완료!
⏱️ 전체 실행 시간: 681.XX초 (11.XX분)
```

### 옵션 2: 실제 서버에서 테스트

```bash
# 서버 재시작
# (서버 시작 명령어)

# 그리고 다시 질문:
# "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘"
```

**확인 위치**:
- 서버 로그 파일에서 `⏱️ PERFORMANCE:` 검색
- 또는 `timings_seconds` 키워드 검색

## 예상 결과 및 대응

### Case 1: Generate Answer가 680초 (99% 확률)

**원인**: LLM 생성 시간 자체가 너무 김

**가능한 최적화**:
1. **max_tokens 감소** (8192 → 2048)
   - 현재: detailed 모드에서 8192 토큰까지 생성
   - 개선: 필요에 따라 동적 조정 (2048-4096)

2. **컨텍스트 크기 감소**
   - 현재: detailed 모드에서 24K chars
   - 개선: 12K-16K로 축소

3. **vLLM 설정 최적화**
   - batch size 증가
   - tensor parallelism 조정

4. **모델 교체 고려**
   - Qwen2.5-72B → 32B 또는 14B 버전

### Case 2: Load Text가 오래 걸림 (1% 확률)

**원인**: BM25 인덱스 로딩 또는 파일 읽기 지연

**최적화**:
- BM25 인덱스 캐싱
- 파일 시스템 최적화

### Case 3: 여러 단계가 고르게 느림

**원인**: 전반적인 시스템 부하

**최적화**:
- 비동기 처리 도입
- 캐싱 전략 수립

## 다음 단계

1. **프로파일링 실행** → 병목 단계 확인
2. **병목 지점 분석** → 로그에서 어느 단계가 오래 걸리는지 확인
3. **최적화 전략 수립** → 병목에 맞는 해결책 적용
4. **재측정** → 개선 효과 검증

---

## 참고: 이전 테스트 결과

### Line 12 (최근 테스트)
```json
{
  "query": "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘",
  "mode": "document",
  "latency_ms": 681455,  // 681초
  "search_results_count": 1
}
```

### 기대 성능
- **목표**: 3-8초
- **현재**: 681초
- **필요 개선**: 85-227배 속도 향상
