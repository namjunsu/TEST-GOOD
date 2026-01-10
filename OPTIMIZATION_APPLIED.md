# vLLM 커뮤니티 검증 기반 성능 최적화 적용

**날짜**: 2026-01-10
**목표**: Document 모드 681초 → 200-300초 (2-3배 속도 향상)

## 문제 진단

### 현재 상황
- **Line 12 테스트 결과**: 681초 (11.4분)
- **파일 크기**: 41KB (매우 작음)
- **결론**: 파일 I/O가 아닌 **LLM 생성 시간**이 병목

### vLLM 커뮤니티 발견 사항

1. **긴 프롬프트 = 느린 속도**
   - 8,000토큰 이상: 속도 20배 저하 (5364 → 273 tokens/s)
   - 출처: [vLLM GitHub Issue #11286](https://github.com/vllm-project/vllm/issues/11286)

2. **과도한 max_tokens**
   - 8192 토큰 생성은 너무 김 (실용적 범위: 2048-4096)
   - 출처: [vLLM Performance Tuning Guide](https://docs.vllm.ai/en/latest/configuration/optimization/)

3. **메모리 압박**
   - 긴 컨텍스트 + 큰 배치 = preemption 증가 → 속도 저하
   - 권장: `max_num_batched_tokens` 감소

## 적용된 최적화

### 1. 컨텍스트 크기 축소 (50%)

**config/constants.py - DocumentHandlerConfig**:

| 항목 | 이전 | 최적화 후 | 감소율 |
|------|------|-----------|--------|
| CONTEXT_WINDOW | 8,000 | 6,000 | 25% |
| CHUNK_CONTEXT_MAX | 24,000 | 12,000 | **50%** |
| CHUNK_SNIPPET_MAX | 6,000 | 4,000 | 33% |
| DETAILED_PREVIEW_LEN | 6,000 | 4,000 | 33% |
| NORMAL_PREVIEW_LEN | 3,000 | 2,000 | 33% |

**효과**: 프롬프트 길이 감소 → 처리 속도 향상

### 2. max_tokens 대폭 감소 (60-75%)

**config/constants.py - DocumentHandlerConfig**:

| 항목 | 이전 | 최적화 후 | 감소율 |
|------|------|-----------|--------|
| DEFAULT_MAX_TOKENS | 1,500 | 1,024 | 32% |
| SUMMARY_MIN_TOKENS | 2,000 | 1,024 | **49%** |
| DETAILED_MIN_TOKENS | 600 | 512 | 15% |
| NORMAL_MIN_TOKENS | 400 | 256 | 36% |

**효과**: 생성 토큰 감소 → 응답 생성 시간 단축

### 3. 동적 토큰 계산 로직 최적화

**app/rag/handlers/document.py - `_calculate_max_tokens()`**:

```python
# 이전: detailed_mode
dynamic_cap = 8192  # 매우 큼!

# 최적화 후
dynamic_cap = 2048  # 75% 감소, vLLM 커뮤니티 권장값
```

**모드별 상한**:
- **자세히 모드**: 8,192 → 2,048 (75% 감소)
- **긴 문서**: 6,144 → 2,048 (67% 감소)
- **중간 문서**: 4,096 → 1,536 (63% 감소)

### 4. 컨텍스트 제한 로직 최적화

**app/rag/handlers/document.py - `_generate_llm_answer()`**:

```python
# 이전
if mode == "detailed":
    context_limit = min(len(full_text), 24000)  # 24K chars

# 최적화 후
if mode == "detailed":
    context_limit = min(len(full_text), 12000)  # 12K chars (50% 감소)
```

## 예상 성능 개선

### 이론적 근거

1. **컨텍스트 50% 감소** (24K → 12K)
   - vLLM 벤치마크: 8K+ 토큰에서 속도 20배 저하
   - 12K chars ≈ 3K 토큰 (한글 기준)
   - **예상 개선**: 1.5-2배

2. **max_tokens 75% 감소** (8192 → 2048)
   - 생성 토큰 수가 선형적으로 시간에 영향
   - **예상 개선**: 1.5-2배

3. **복합 효과**
   - 컨텍스트 감소 × max_tokens 감소
   - **예상 총 개선**: 2-3배

### 성능 예측

| 항목 | 이전 | 예상 |
|------|------|------|
| 전체 시간 | 681초 (11.4분) | **200-300초 (3-5분)** |
| Load Text | ~1초 | ~1초 (변화 없음) |
| Generate Answer | ~680초 | **200-300초** |

## 품질 영향 분석

### 유지되는 품질

1. **12K chars 컨텍스트**
   - 여전히 충분한 문서 내용 포함
   - 41KB PDF ≈ 전체 내용의 30-50%
   - 핵심 정보는 충분히 확보

2. **2048 토큰 응답**
   - 한글 기준 약 1500-2000자
   - 상세한 답변에 충분한 길이
   - 실제 대부분의 답변은 1000-1500 토큰 내

### 트레이드오프

| 측면 | 손실 | 이득 |
|------|------|------|
| 상세도 | 약간 감소 (매우 긴 응답 불가) | 여전히 충분히 상세 |
| 컨텍스트 | 문서 일부만 참조 | 핵심 정보는 포함 |
| 속도 | - | **2-3배 향상** |

## 테스트 방법

### 옵션 1: 서버 재시작 후 실제 테스트

```bash
# 서버 재시작
# (서버 시작 명령어)

# 같은 쿼리 실행
# "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘"
```

**확인 지표**:
- 로그에서 `⏱️ PERFORMANCE:` 검색
- `timings_seconds` 확인
- **목표**: Generate Answer 단계가 200-300초

### 옵션 2: 독립 프로파일링 스크립트

```bash
python3 scripts/profile_document_performance.py
```

## 추가 최적화 가능성

만약 200-300초도 여전히 느리다면:

### vLLM 서버 설정 최적화

```python
# vLLM 서버 시작 시
--max-num-batched-tokens 2048      # 기본값에서 감소
--max-num-seqs 4                   # 동시 요청 수 감소
--gpu-memory-utilization 0.95      # 메모리 활용 증가
```

### 모델 경량화 고려

- Qwen2.5-72B-AWQ → Qwen2.5-32B (속도 2배)
- 또는 Qwen2.5-14B (속도 5배)

## 참고 자료

1. [vLLM Optimization Guide](https://docs.vllm.ai/en/latest/configuration/optimization/)
2. [Long Context Performance Issue](https://github.com/vllm-project/vllm/issues/11286)
3. [vLLM Performance Tuning - Google Cloud](https://cloud.google.com/blog/topics/developers-practitioners/vllm-performance-tuning-the-ultimate-guide-to-xpu-inference-configuration)
4. [Sparse RAG - ICLR 2025](https://openreview.net/pdf?id=HE6pJoNnFp)
5. [RAG Inference Survey 2025](https://arxiv.org/html/2506.00054v1)

## 롤백 방법

만약 품질이 너무 떨어진다면:

```bash
git diff config/constants.py
git diff app/rag/handlers/document.py

# 특정 값만 조정 (예: CHUNK_CONTEXT_MAX를 16K로)
# 또는 전체 롤백
git checkout config/constants.py
git checkout app/rag/handlers/document.py
```

---

**다음 단계**: 서버 재시작 후 성능 테스트 및 검증
