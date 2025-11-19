# Module Atlas - RAG System
Generated: 2025-11-14 11:19:37

## Module Details

### app/__init__.py [✅ USED]
- **Lines of Code**: 6
- **Module Doc**: AI-CHAT Application Package

Version: 2.0.0...
- **Coverage**: 100.0% (1/1 lines)

### app/alerts.py [🔗 REACHABLE]

### app/api/__init__.py [❌ UNUSED]
- **Lines of Code**: 1
- **Module Doc**: API 모듈...
- **Coverage**: 0.0% (0/0 lines)

### app/api/main.py [✅ USED]
- **Lines of Code**: 367
- **Module Doc**: FastAPI 백엔드 서버

Health check 및 기타 API 엔드포인트 제공...
- **Entry Point**: Yes ⚡
- **Functions**:
  - `get_public_base_url(request...)`
  - `log_file_access(filename, action, query...)`
  - `health(...)`
  - `preview_file(ref...)`
  - `download_file(ref...)`
- **Coverage**: 31.9% (46/144 lines)

### app/config/__init__.py [❌ UNUSED]
- **Lines of Code**: 1
- **Coverage**: 0.0% (0/0 lines)

### app/config/compat.py [❌ UNUSED]

### app/config/performance_compat.py [❌ UNUSED]

### app/config/settings.py [✅ USED]
- **Lines of Code**: 55
- **Module Doc**: 프로젝트 통합 설정 모듈
네임 충돌 방지를 위해 절대 경로로 임포트: from app.config.settings import ......
- **Coverage**: 90.0% (18/20 lines)

### app/core/__init__.py [✅ USED]
- **Lines of Code**: 31
- **Module Doc**: Core Application Infrastructure

핵심 인프라 모듈:
- config: 설정 관리
- logging: 로깅 시스템
- errors: 예외 정의...
- **Coverage**: 100.0% (3/3 lines)

### app/core/errors.py [✅ USED]
- **Lines of Code**: 121
- **Module Doc**: 애플리케이션 예외 정의

계층적 예외 구조:
- AppError (기본)
  - ConfigError (설정)
  - DatabaseError (데이터베이스)
  - ModelEr...
- **Classes**:
  - `AppError` (2 methods)
  - `ConfigError` 
  - `DatabaseError` 
  - `ModelError` 
  - `SearchError` 
- **Functions**:
  - `__init__(self, message, details...)`
  - `__str__(self...)`
- **Coverage**: 97.1% (33/34 lines)

### app/core/logging.py [✅ USED]
- **Lines of Code**: 104
- **Module Doc**: 통합 로깅 시스템

모든 모듈은 이 모듈의 get_logger()를 사용합니다.

Example:
    >>> from app.core.logging import get_logg...
- **Functions**:
  - `_init_logger(...)`
  - `get_logger(name...)`
  - `set_level(level...)`
- **Coverage**: 91.9% (34/37 lines)

### app/data/__init__.py [❌ UNUSED]

### app/data/amount_parser_v2.py [🔗 REACHABLE]

### app/data/metadata_db.py [❌ UNUSED]

### app/extractors/__init__.py [❌ UNUSED]

### app/extractors/device_fields.py [❌ UNUSED]

### app/extractors/finance.py [❌ UNUSED]

### app/extractors/merge.py [❌ UNUSED]

### app/index/__init__.py [❌ UNUSED]

### app/index/bm25_store.py [❌ UNUSED]

### app/logging/config.py [🔗 REACHABLE]

### app/prompts/document_prompts.py [❌ UNUSED]

### app/query/__init__.py [❌ UNUSED]

### app/query/filters.py [❌ UNUSED]

### app/rag/__init__.py [✅ USED]
- **Lines of Code**: 15
- **Module Doc**: RAG (Retrieval-Augmented Generation) Module

핵심 컴포넌트:
- pipeline: RAG 파사드 (단일 진입점)
- metrics: 성능 지표 ...
- **Coverage**: 100.0% (2/2 lines)

### app/rag/cache_manager.py [❌ UNUSED]

### app/rag/cache_namespace.py [❌ UNUSED]

### app/rag/metrics_collector.py [🔗 REACHABLE]

### app/rag/parallel_executor.py [❌ UNUSED]

### app/rag/parse/__init__.py [✅ USED]
- **Lines of Code**: 6
- **Module Doc**: RAG 파싱 모듈...
- **Coverage**: 100.0% (3/3 lines)

### app/rag/parse/doctype.py [✅ USED]
- **Lines of Code**: 206
- **Module Doc**: 문서 유형(doctype) 분류기
- 룰 기반 분류 (키워드 매칭)
- 다중 매칭 시 우선순위 적용
- config/document_processing.yaml 설정 기반...
- **Classes**:
  - `DocumentTypeClassifier` (6 methods)
- **Functions**:
  - `get_classifier(...)`
  - `classify_document(text, filename...)`
  - `__init__(self, config_path...)`
  - `_load_config(self...)`
  - `_get_default_config(self...)`
- **Coverage**: 22.2% (14/63 lines)

### app/rag/parse/parse_meta.py [✅ USED]
- **Lines of Code**: 361
- **Module Doc**: 메타데이터 파싱 모듈
2025-10-26

문서 날짜와 카테고리를 표준화합니다.

규칙:
- 날짜: 기안일자 우선, 시행일자 폴백, 둘 다 표시
- 카테고리: 규칙 기반 분류, "...
- **Classes**:
  - `MetaParser` (8 methods)
- **Functions**:
  - `__init__(self, config_path...)`
  - `_validate_author(self, author...)`
  - `_load_config(self, config_path...)`
  - `parse_dates(self, metadata...)`
  - `_normalize_date(self, date_str...)`
- **Coverage**: 9.4% (14/149 lines)

### app/rag/parse/parse_tables.py [✅ USED]
- **Lines of Code**: 323
- **Module Doc**: 표(비용) 파싱 모듈
2025-10-26

문서에서 비용 표를 파싱하고 합계를 검증합니다.

기능:
- 헤더 자동 인식 (모델명, 수리내역, 수량, 단가, 합계 등)
- 숫자 정규...
- **Classes**:
  - `TableParser` (9 methods)
- **Functions**:
  - `__init__(self, config_path...)`
  - `_load_config(self, config_path...)`
  - `normalize_number(self, text...)`
  - `detect_table_headers(self, text...)`
  - `extract_cost_table(self, text...)`
- **Coverage**: 12.6% (16/127 lines)

### app/rag/persistent_cache.py [❌ UNUSED]

### app/rag/pipeline.py [✅ USED]
- **Lines of Code**: 2140
- **Module Doc**: RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline =...
- **Classes**:
  - `RAGRequest` 
  - `RAGResponse` 
  - `Retriever` (1 methods)
  - `Compressor` (1 methods)
  - `Generator` (1 methods)
- **Functions**:
  - `_encode_file_ref(filename...)`
  - `search(self, query, top_k...)`
  - `compress(self, chunks, ratio...)`
  - `generate(self, query, context...)`
  - `__init__(self, retriever, compressor...)`
- **Coverage**: 29.3% (203/692 lines)

### app/rag/preprocess/__init__.py [✅ USED]
- **Lines of Code**: 5
- **Module Doc**: RAG 전처리 모듈...
- **Coverage**: 100.0% (2/2 lines)

### app/rag/preprocess/clean_text.py [✅ USED]
- **Lines of Code**: 280
- **Module Doc**: 텍스트 노이즈 제거 모듈
2025-10-26

문서에서 프린트 타임스탬프, URL, 반복 헤더/푸터 등의 노이즈를 제거합니다....
- **Classes**:
  - `TextCleaner` (9 methods)
- **Functions**:
  - `__init__(self, config_path...)`
  - `_load_config(self, config_path...)`
  - `_compile_patterns(self...)`
  - `clean(self, text...)`
  - `_remove_pattern_noise(self, lines...)`
- **Coverage**: 31.7% (40/126 lines)

### app/rag/query_expander.py [❌ UNUSED]

### app/rag/query_parser.py [✅ USED]
- **Lines of Code**: 197
- **Module Doc**: 쿼리 파싱 모듈 - Closed-World Validation
기안자/연도 추출을 메타데이터 DB 기반으로 검증...
- **Classes**:
  - `QueryParser` (9 methods)
- **Functions**:
  - `parse_filters_simple(query, known_drafters...)`
  - `__init__(self, known_drafters...)`
  - `_load_stopwords(self...)`
  - `_load_token_patterns(self...)`
  - `parse_filters(self, query...)`
- **Coverage**: 89.8% (88/98 lines)

### app/rag/query_router.py [✅ USED]
- **Lines of Code**: 303
- **Module Doc**: 쿼리 모드 라우터
2025-10-26

질의 의도를 분석하여 Q&A 모드 vs 문서 미리보기 모드를 결정합니다.

규칙:
- Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모...
- **Classes**:
  - `QueryMode` 
  - `QueryRouter` (5 methods)
- **Functions**:
  - `_norm(s...)`
  - `_score(qn, tn...)`
  - `__init__(self, config_path...)`
  - `_load_config(self, config_path...)`
  - `classify_mode(self, query...)`
- **Coverage**: 58.8% (70/119 lines)

### app/rag/retrievers/__init__.py [✅ USED]
- **Lines of Code**: 15
- **Module Doc**: 검색 엔진 모듈

구현체:
- hybrid: 하이브리드 검색 (BM25 + Dense) - QuickFixRAG 래퍼
- bm25: BM25 검색 (TODO)
- dense: De...
- **Coverage**: 100.0% (2/2 lines)

### app/rag/retrievers/exact_match.py [❌ UNUSED]

### app/rag/retrievers/hybrid.py [✅ USED]
- **Lines of Code**: 93
- **Module Doc**: 하이브리드 검색 엔진 (MetadataDB 기반 임시 구현)

QuickFixRAG가 제거되어 MetadataDB를 사용한 간단한 검색으로 대체...
- **Classes**:
  - `HybridRetriever` (2 methods)
- **Functions**:
  - `__init__(self...)`
  - `search(self, query, top_k...)`
- **Coverage**: 76.5% (26/34 lines)

### app/rag/routing/__init__.py [❌ UNUSED]

### app/rag/routing/anchor_scorer.py [❌ UNUSED]

### app/rag/routing/profile_matcher.py [❌ UNUSED]

### app/rag/routing_monitor.py [❌ UNUSED]

### app/rag/smart_cache_key.py [🔗 REACHABLE]

### app/rag/summary_templates.py [❌ UNUSED]
- **Lines of Code**: 477
- **Module Doc**: 문서 유형별 요약 프롬프트 템플릿 (v2)
2025-10-27

목적: 문서 타입 자동 감지 + 맞춤 프롬프트로 요약 품질 급상승
핵심: "틀 채우기" 제거, "진짜 읽고 정리" ...
- **Functions**:
  - `detect_doc_kind(filename, text...)`
  - `_recheck_money_and_decision(text, claimed_total...)`
  - `build_prompt(kind, filename, drafter...)`
  - `parse_summary_json(response...)`
  - `format_summary_output(parsed_json, kind, filename...)`
- **Coverage**: 0.0% (0/190 lines)

### app/rag/utils/__init__.py [❌ UNUSED]
- **Lines of Code**: 1
- **Coverage**: 0.0% (0/0 lines)

### app/rag/utils/context_hydrator.py [✅ USED]
- **Lines of Code**: 157
- **Module Doc**: Context Hydrator - 청크에서 텍스트 추출 및 PDF 보강...
- **Functions**:
  - `hydrate_context(chunks, max_len...)`
  - `_extract_text_from_chunk(chunk, metrics...)`
  - `_extract_pdf_tail(chunk, metrics, needed...)`
- **Coverage**: 44.7% (34/76 lines)

### app/rag/utils/json_utils.py [✅ USED]
- **Lines of Code**: 206
- **Module Doc**: JSON 파싱 유틸리티 (강건한 파서)...
- **Functions**:
  - `extract_last_json_block(s...)`
  - `parse_summary_json_robust(response...)`
  - `ensure_citations(json_data, doc_ref...)`
  - `extract_amounts_from_text(text...)`
  - `validate_numeric_fields(json_data, source_text...)`
- **Coverage**: 10.5% (10/95 lines)

### app/textproc/normalizer.py [🔗 REACHABLE]

### app/utils/sqlite_helpers.py [❌ UNUSED]

### app/utils/text_normalizer.py [❌ UNUSED]
