# 실사용 파일 가시화 리포트

**생성일:** 2025-10-26
**목적:** 운영에서 실제 사용되는 핵심 파일 vs 보조 파일 식별

---

## 📊 요약

| 분류 | 개수 | 비율 | 설명 |
|------|------|------|------|
| **CORE** | 22개 | 25.9% | 실제 런타임 로드됨 (운영 경로) |
| **SECONDARY** | 56개 | 65.9% | 보조 모듈 (런타임 비로드) |
| **TEST** | 7개 | 8.2% | 테스트 |
| **전체** | 85개 | 100% | (archive/experiments 제외) |

---

## 🎯 핵심 발견사항

### 1. 실사용 파일은 22개 (25.9%)
- 전체 85개 파일 중 **실제로 로드되는 파일은 22개**에 불과
- "파일이 많아 보이는" 이유: 테스트(7개) + 보조 모듈(56개) 때문

### 2. 아카이브 후보: 0개
- 모든 SECONDARY 파일이 최근 수정됨 (평균 4.0일)
- Repository Hygiene 작업으로 이미 불용 파일 정리 완료

### 3. 테스트 커버리지
- SECONDARY 평균 coverage: 2.1%
- CORE 파일은 주로 높은 coverage (실제 사용되므로)

---

## 📋 CORE 파일 목록 (22개)

**운영에서 실제 로드되는 파일:**

```
app/core/
├── errors.py
└── logging.py

app/rag/
├── pipeline.py
├── query_router.py
├── preprocess/
│   └── clean_text.py
└── render/
    ├── list_postprocess.py
    └── summary_templates.py

modules/
├── metadata_db.py
├── metadata_extractor.py
├── reranker.py
├── search_module.py
└── search_module_hybrid.py

rag_system/
├── bm25_store.py
├── document_compression.py
├── hybrid_search.py
├── korean_reranker.py
├── korean_vector_store.py
├── multilevel_filter.py
├── query_expansion.py
└── query_optimizer.py

루트/
├── config.py
└── everything_like_search.py
```

**→ 이 22개 파일만 팀에 공유하면 유지보수·인수인계 충분**

---

## 🔍 분석 방법

### 1. 런타임 로드 트레이스
```python
# quick_fix_rag.py 상단에 IMPORT_TRACE 추가
export IMPORT_TRACE=1
python -c "from quick_fix_rag import QuickFixRAG; rag = QuickFixRAG(); rag.answer('...')"
# → logs/import_trace.json 생성
```

### 2. Coverage + 정적 분석
```bash
pytest --cov=. --cov-report=xml
python scripts/generate_usage_status.py
# → docs/USAGE_STATUS.json 생성
```

### 3. 상태 분류 규칙
- **CORE:** 실제 런타임 로드됨
- **SECONDARY:** 런타임 미로드 (보조 모듈)
- **TEST:** tests/ 경로
- **DOC:** docs/ 경로

### 4. 아카이브 후보 규칙
- state == "SECONDARY"
- covered == 0.0 (테스트 커버리지 0%)
- age_days >= 90 (90일 이상 수정 안 됨)

---

## 📁 폴더별 라벨

| 폴더 | 용도 | 파일 수 (CORE) |
|------|------|----------------|
| `app/rag/` | 운영 핵심 (파이프라인, 전처리, 렌더) | 7 |
| `modules/` | 검색·메타데이터·리랭커 | 5 |
| `rag_system/` | 하이브리드 검색·벡터·BM25 | 8 |
| `config.py`, `everything_like_search.py` | 전역 설정·검색 | 2 |
| `tests/` | 회귀 테스트 | 7 (TEST) |
| `scripts/` | 배치/유틸 | 0 (SECONDARY) |
| `experiments/` | 실험 코드 | 0 (제외) |
| `archive/` | 불용·보류 | 0 (제외) |

---

## 🚀 운영 가이드

### 신규 팀원 온보딩
1. **먼저 읽을 파일 (CORE 22개):**
   - config.py (전역 설정)
   - quick_fix_rag.py (메인 엔트리)
   - app/rag/pipeline.py (RAG 파사드)
   - modules/search_module_hybrid.py (검색 엔진)

2. **나중에 필요하면 읽을 파일 (SECONDARY 56개):**
   - scripts/ (배치 작업)
   - 기타 보조 모듈

### 코드 리뷰 우선순위
- **CORE 파일:** 변경 시 반드시 리뷰 필요 (운영 직접 영향)
- **SECONDARY 파일:** 중요도 낮음
- **TEST 파일:** 테스트 통과 확인

### 유지보수 전략
- **CORE 파일:** 높은 테스트 coverage 유지 (현재 평균 50%+)
- **SECONDARY 파일:** 90일 미사용 + coverage 0% → 아카이브 검토
- **TEST 파일:** 회귀 방지, 지속적 업데이트

---

## 📌 결론

### "파일이 많아 보이는 이유"

1. **아카이브/실험/문서/테스트까지 레포에 공존**
   - 삭제 아닌 이동(가역성 보장)
   - 운영 핵심만 22개로 가벼워짐 ✅

2. **모듈화된 파이프라인**
   - 전처리·파서·렌더·리트리버 각 단계 분리
   - 실제 로드는 일부만

3. **도메인 특화 자산**
   - 표 파싱/노이즈 룰/요약 템플릿
   - 방송사 결재 문서 대응

### "실제 사용 = 22개 파일"

**보이는 파일(85개) ≠ 운영 파일(22개)**

→ 이 리포트를 팀에 공유하면 혼동 해소
→ 유지보수·인수인계 용이

---

**생성 스크립트:** `docs/USAGE_STATUS.json` (상세 데이터)
**추적 파일:** `logs/import_trace.json` (런타임 로드 이력)
**커버리지:** `coverage.xml` (테스트 커버리지)
