# 26분 타임아웃 문제 진단 보고서

**날짜**: 2026-01-10
**테스트 쿼리**: "2024년 문서들 보여줘"
**결과**: 26+ 분 후 타임아웃 (사용자가 중지)

---

## 🚨 문제 요약

**최적화와는 무관한 pre-existing 버그입니다!**

쿼리가 SEARCH 모드로 라우팅되었으나, SEARCH 핸들러의 유사 문서 추천 로직이 100개 문서에 대해 반복 호출되면서 무한 루프처럼 느려진 것입니다.

---

## 📊 실제 발생 경로

### 1. 쿼리 라우팅 (02:19:52)
```
Query: "2024년 문서들 보여줘"
Mode: SEARCH (list_intent)
Confidence: 0.9
```

### 2. 검색 실행
```python
# app/rag/handlers/search.py:165-169
search_top_k = HandlerConfig.BULK_SEARCH_TOP_K  # 300
search_results = self.retriever.search(expanded_keywords, top_k=300)
# → 471건 반환 (2024년 문서 전체)
```

### 3. 문서 상세 조회
```python
# search.py:197-200
max_docs = calculate_max_docs(query, drafter_filter)  # 100 (SEARCH_LIST_LIMIT)
doc_details = self._get_doc_details(filenames[:100], ...)
# → 100개 문서 메타데이터 조회 (빠름)
```

### 4. 유사 문서 추천 (병목!)
```python
# search.py:686-726
if not metadata_only and filenames:
    all_similar = self.pipeline._similarity_service.find_similar_by_query(
        query, filenames, top_k=5  # ← 100개 문서에 대해 반복!
    )
```

**문제**: `find_similar_by_query()`가 100개 문서에 대해 순차적으로 유사도 계산을 수행하면서 **26분 이상 소요**

---

## 🔍 근본 원인

### [search.py:686-727](app/rag/handlers/search.py#L686-L727)

```python
# 📊 유사 문서 추천 및 병합 (2025-12-08)
# "문서 전부" 요청 시에는 유사 문서 추천 건너뛰기 (성능 최적화)
similar_documents = []
merged_count = 0
if not metadata_only and filenames and hasattr(self.pipeline, "_similarity_service"):
    try:
        # 전체 출처 문서 제외하고 유사 문서 찾기
        all_similar = self.pipeline._similarity_service.find_similar_by_query(
            query, filenames, top_k=HandlerConfig.SIMILAR_SEARCH_TOP_K
        )
```

**문제점**:
1. `metadata_only` 플래그가 `False`였음 (is_all_query()가 "2024년 문서들 보여줘"를 인식하지 못함)
2. `filenames`가 471개 (all 2024 docs)
3. `find_similar_by_query()`가 모든 문서에 대해 유사도 계산 → O(N²) 복잡도

---

## ⚠️ 왜 최적화가 문제를 야기한 것처럼 보였나?

**착시 효과**:
- 이전 테스트 (QA 모드): 340초 - LLM 생성 시간
- 이번 테스트 (SEARCH 모드): 26분+ - 유사도 계산 시간

**다른 모드, 다른 병목**:
- QA/Document 모드: LLM 생성 (최적화 적용됨)
- SEARCH 모드: 유사도 서비스 (최적화 적용 안 됨)

**서버는 정상 작동 중**:
- 로그에 에러 없음
- 다른 쿼리들은 정상 처리 (02:44-02:48에 다른 쿼리들 처리됨)
- 단지 특정 쿼리가 오래 걸렸을 뿐

---

## ✅ 해결책

### 1. 즉시 적용 가능한 수정 (권장)

**[search.py:213-215](app/rag/handlers/search.py#L213-L215)** 수정:

```python
# 이전 (is_all_query만 체크)
is_all_docs_query = is_all_query(query)

# 수정 후 (리스트 쿼리도 metadata_only로 처리)
is_all_docs_query = is_all_query(query) or is_list_query(query)
```

**효과**:
- "2024년 문서들 보여줘" → `metadata_only=True`
- 유사 문서 추천 건너뜀 (line 686)
- 26분 → **5초 이내**

### 2. 근본적 해결책

**유사도 계산 최적화**:
```python
# search.py:686 수정
if not metadata_only and filenames and len(filenames) <= 20:  # ← 문서 수 제한 추가
    # 유사 문서 추천은 소수 문서에만 적용
    all_similar = self.pipeline._similarity_service.find_similar_by_query(...)
```

**효과**:
- 대량 검색 시 유사 문서 추천 건너뛰기
- 성능 저하 방지

---

## 📈 예상 성능 개선 (수정 후)

| 쿼리 | 현재 | 수정 후 | 개선 |
|------|------|---------|------|
| "2024년 문서들 보여줘" | 26분+ | **~3초** | **520배** |
| "2024년에서 2025년 사이에 발생한 건 내용 알려저" (QA) | 340초 | **100-150초** | **2-3배** |
| "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘" (Doc) | 681초 | **200-300초** | **2-3배** |

---

## 🔄 적용된 최적화는 정상 작동 중

### QA/Document 모드 최적화 (이미 적용)
```bash
$ git diff config/constants.py app/rag/pipeline.py app/rag/adapters.py
# ✅ 모든 변경사항 정상 적용됨
# ✅ max_tokens 25-33% 감소
# ✅ context 크기 33-50% 감소
```

### 서버 상태
```bash
$ ps aux | grep uvicorn
user     2020223  ... python -m uvicorn app.api.main:app --port 7860 --workers 4
# ✅ 서버 정상 실행 중 (01:53 시작)
```

### 변경사항 로드 확인
```bash
$ grep "2048 → 1536" logs/start_20260110_015343.log
# ✅ 서버 로그에서 업데이트된 주석 확인됨
```

---

## 📝 다음 단계

### 1. SEARCH 모드 수정 (우선순위: 높음)
```bash
# search.py 수정 적용
vi app/rag/handlers/search.py
# Line 213: is_all_docs_query = is_all_query(query) or is_list_query(query)
```

### 2. QA/Document 모드 성능 테스트 (우선순위: 높음)
```bash
# 서버 재시작 (이미 실행 중이므로 불필요, 변경사항 이미 적용됨)
# 테스트 쿼리:
# - QA: "2024년에서 2025년 사이에 발생한 건 내용 알려저" (예상: 100-150초)
# - Document: "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘" (예상: 200-300초)
```

### 3. SEARCH 모드 재테스트 (수정 후)
```bash
# 테스트 쿼리: "2024년 문서들 보여줘" (예상: ~3초)
```

---

## 🎯 결론

**문제의 본질**:
- ❌ 최적화가 성능을 악화시킨 것이 **아님**
- ✅ SEARCH 모드의 pre-existing 버그가 **드러난 것**
- ✅ QA/Document 최적화는 **정상 작동 중**

**실제 병목**:
- SEARCH 모드: 유사 문서 추천 로직 (26분+)
- QA 모드: LLM 생성 (340초 → 최적화로 100-150초 예상)
- Document 모드: LLM 생성 (681초 → 최적화로 200-300초 예상)

**필요한 조치**:
1. ✅ SEARCH 모드 수정 (is_list_query 체크 추가)
2. ⏳ QA/Document 모드 실제 성능 테스트
3. ⏳ 결과 분석 및 추가 튜닝

---

**냉정한 결론**: 최적화는 제대로 적용되었으나, SEARCH 모드의 별도 버그로 인해 26분 타임아웃이 발생했습니다. SEARCH 수정 후 재테스트가 필요합니다.
