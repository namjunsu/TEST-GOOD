# RAG 레포 사용 경로 맵

**생성일:** 2025-10-26
**목적:** 사용 중인 파일과 미사용/실험 파일 식별

## 핵심 엔트리포인트

| 파일 | 용도 | 호출 경로 |
|------|------|----------|
| `start_ai_chat.sh` | 메인 실행 스크립트 | 직접 실행 |
| `web_interface.py` | Streamlit UI | start_ai_chat.sh → streamlit run |
| `app/api/main.py` | FastAPI 백엔드 | start_ai_chat.sh → uvicorn |
| `quick_fix_rag.py` | RAG 엔진 (P0 핫픽스 적용) | web_interface.py, app/api/main.py |

## 파일 분류 (자동 분석 + 수동 검토)

### 🟢 핵심 (Core - 운영 필수)

**app/core/**
- ✅ `app/core/logging.py` - 표준 로깅
- ✅ `app/core/errors.py` - 에러 코드
- ✅ `app/__init__.py` - 패키지 초기화
- ✅ `app/core/__init__.py` - 코어 패키지

**app/rag/** (RAG 파이프라인)
- ✅ `app/rag/pipeline.py` - RAG 파사드 (web_interface.py에서 사용)
- ✅ `app/rag/query_router.py` - 모드 라우팅 (2025-10-26 추가)
- ✅ `app/rag/preprocess/clean_text.py` - 노이즈 제거 (2025-10-26 추가)
- ✅ `app/rag/parse/parse_meta.py` - 메타 파싱 (2025-10-26 추가)
- ✅ `app/rag/parse/parse_tables.py` - 표 파싱 (2025-10-26 추가)
- ✅ `app/rag/render/summary_templates.py` - 요약 템플릿 (2025-10-26 추가)

**quick_fix_rag.py**
- ✅ `quick_fix_rag.py` - 실제 사용 중인 RAG 엔진 (P0 + 경화 완료)

**modules/** (검색 모듈)
- ✅ `modules/search_module_hybrid.py` - 하이브리드 검색 (quick_fix_rag.py에서 사용)
- ✅ `modules/reranker.py` - L2 리랭커 (quick_fix_rag.py에서 사용)

**rag_system/** (RAG 시스템 코어)
- ✅ `rag_system/hybrid_search.py` - 하이브리드 검색 엔진
- ✅ `rag_system/korean_vector_store.py` - 한국어 벡터 스토어
- ✅ `rag_system/bm25_store.py` - BM25 인덱스
- ✅ `rag_system/query_optimizer.py` - 쿼리 최적화
- ✅ `rag_system/qwen_llm.py` - LLM 인터페이스
- ✅ `rag_system/multilevel_filter.py` - 다단계 필터

**config.py**
- ✅ `config.py` - 전역 설정

**config/**
- ✅ `config/document_processing.yaml` - 문서 처리 설정 (2025-10-26 추가)

### 🟡 공용 (Utils/Components - 간접 사용)

**components/** (UI 컴포넌트)
- ✅ `components/chat_interface.py` - 채팅 인터페이스 (web_interface.py)
- ✅ `components/sidebar_library.py` - 사이드바 (web_interface.py)
- ✅ `components/document_preview.py` - 문서 미리보기 (web_interface.py)
- ✅ `components/pdf_viewer.py` - PDF 뷰어 (web_interface.py)

**utils/**
- ✅ `utils/css_loader.py` - CSS 로더 (web_interface.py)
- ✅ `utils/document_loader.py` - 문서 로더 (web_interface.py)
- ✅ `utils/system_checker.py` - 시스템 검증 (start_ai_chat.sh)
- ✅ `utils/session_manager.py` - 세션 관리
- ✅ `utils/performance.py` - 성능 측정
- ✅ `utils/error_handler.py` - 에러 핸들러

**modules/**
- ✅ `modules/search_module.py` - 기본 검색 (하이브리드의 폴백)
- ✅ `modules/metadata_db.py` - 메타데이터 DB 접근

### 🟠 테스트 (Tests - 회귀 방지)

**tests/**
- ✅ `tests/test_filename_matching.py` - 파일명 매칭 테스트 (2025-10-26)
- ✅ `tests/test_clean_text.py` - 노이즈 제거 테스트 (2025-10-26)
- ✅ `tests/test_parse_meta.py` - 메타 파싱 테스트 (2025-10-26)
- ✅ `tests/test_parse_table.py` - 표 파싱 테스트 (2025-10-26)
- ⚠️ `test_l2_rag.py` - L2 RAG 스모크 테스트 (루트, 이동 필요)

### 🔴 실험/임시 (Experimental - 이동 대상)

**루트 레벨 테스트/진단 스크립트**
- 🔴 `test_author_fix.py` - 저자 검색 테스트 (임시)
- 🔴 `diagnose_rag.py` - RAG 진단 도구 (디버그용)
- 🔴 `test_refactoring_final.py` - 리팩토링 테스트 (임시)
- 🔴 `quick_rebuild_bm25.py` - BM25 재구축 (유틸리티)

**app/rag/ 미사용**
- 🔴 `app/rag/db.py` - 사용 안 됨 (metadata_db.py로 대체)
- 🔴 `app/rag/index_bm25.py` - 사용 안 됨 (rag_system/bm25_store.py 사용)
- 🔴 `app/rag/index_vec.py` - 사용 안 됨 (rag_system/korean_vector_store.py 사용)
- 🔴 `app/rag/metrics.py` - 사용 안 됨
- 🔴 `app/rag/retriever_v2.py` - 구버전 (사용 안 됨)
- 🔴 `app/rag/retrievers/hybrid.py` - 사용 안 됨 (rag_system/hybrid_search.py 사용)

**app/data/**
- 🔴 `app/data/metadata/db.py` - 사용 안 됨 (modules/metadata_db.py로 대체)
- 🔴 `app/data/metadata/db_compat.py` - 호환성 레이어 (불필요)

**app/indexer/**
- 🔴 `app/indexer/__init__.py` - 빈 패키지

**app/ops/**
- 🔴 `app/ops/__init__.py` - 빈 패키지

**app/ui/**
- 🔴 `app/ui/__init__.py` - 빈 패키지 (컴포넌트는 components/ 사용)

**auto_indexer.py**
- 🔴 `auto_indexer.py` - 자동 인덱싱 (유틸리티, 주기적 실행용)

**rag_system/ 미사용**
- 🔴 `rag_system/ensemble_reranker.py` - 앙상블 리랭커 (사용 안 됨, modules/reranker.py 사용)

### ⚪ 불확실 (검토 필요)

**rag_system/**
- ⚪ `rag_system/__init__.py` - 패키지 초기화 (import 경로 확인 필요)

## 이동 계획

### Phase 1: 실험/임시 → experiments/claude/20251026/

```bash
# 루트 레벨 테스트 스크립트
test_author_fix.py → experiments/claude/20251026/
diagnose_rag.py → experiments/claude/20251026/
test_refactoring_final.py → experiments/claude/20251026/
test_l2_rag.py → tests/  # 테스트이므로 tests/로 이동
```

### Phase 2: 불용 코드 → archive/20251026/

```bash
# app/rag/ 미사용
app/rag/db.py → archive/20251026/app/rag/
app/rag/index_bm25.py → archive/20251026/app/rag/
app/rag/index_vec.py → archive/20251026/app/rag/
app/rag/metrics.py → archive/20251026/app/rag/
app/rag/retriever_v2.py → archive/20251026/app/rag/
app/rag/retrievers/hybrid.py → archive/20251026/app/rag/retrievers/

# app/data/ 미사용
app/data/ → archive/20251026/app/  # 전체 디렉터리

# 빈 패키지
app/indexer/ → archive/20251026/app/
app/ops/ → archive/20251026/app/
app/ui/ → archive/20251026/app/

# rag_system/ 미사용
rag_system/ensemble_reranker.py → archive/20251026/rag_system/
```

### Phase 3: 유틸리티 정리

```bash
# 유틸리티 스크립트 (필요 시 사용)
quick_rebuild_bm25.py → scripts/  # 유틸리티는 scripts/로
auto_indexer.py → scripts/  # 주기 실행 스크립트
```

## 영향도 분석

| 이동 대상 | import 영향도 | 리스크 |
|----------|-------------|--------|
| test_* (루트) | 없음 (독립 실행) | 낮음 |
| app/rag/db.py | ❌ 사용 안 됨 | 없음 |
| app/rag/index_*.py | ❌ 사용 안 됨 | 없음 |
| app/data/ | ❌ 사용 안 됨 | 없음 |
| 빈 패키지 | ⚠️ import 에러 가능 | 중간 (테스트 필요) |

## 검증 체크리스트

이동 후 검증:

- [ ] `python -c "from app.rag.pipeline import RAGPipeline; print('✓')"` - import 확인
- [ ] `python quick_fix_rag.py` - 엔트리포인트 확인
- [ ] `python -m pytest tests/test_filename_matching.py -v` - 테스트 통과
- [ ] `bash start_ai_chat.sh` - 실행 확인

## 주의사항

1. **metadata.db** - 절대 이동/삭제 금지
2. **logs/** - 절대 이동/삭제 금지
3. **data/extracted/** - 텍스트 추출 경로, 이동 금지
4. **.venv/** - 가상환경, 제외
5. **config.py, config/*.yaml** - 설정 파일, 유지
