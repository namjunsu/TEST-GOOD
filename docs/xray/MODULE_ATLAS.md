# Module Atlas - RAG System
Generated: 2025-10-30 12:39:30

## Module Details

### app/__init__.py [❌ UNUSED]
- **Lines of Code**: 6
- **Module Doc**: AI-CHAT Application Package

Version: 2.0.0...
- **Coverage**: 0.0% (0/1 lines)

### app/api/__init__.py [❌ UNUSED]
- **Lines of Code**: 1
- **Module Doc**: API 모듈...
- **Coverage**: 0.0% (0/0 lines)

### app/api/main.py [🔗 REACHABLE]
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
- **Coverage**: 0.0% (0/144 lines)

### app/config/__init__.py [❌ UNUSED]
- **Lines of Code**: 1
- **Coverage**: 0.0% (0/0 lines)

### app/config/settings.py [❌ UNUSED]
- **Lines of Code**: 55
- **Module Doc**: 프로젝트 통합 설정 모듈
네임 충돌 방지를 위해 절대 경로로 임포트: from app.config.settings import ......
- **Coverage**: 0.0% (0/20 lines)

### app/core/__init__.py [❌ UNUSED]
- **Lines of Code**: 31
- **Module Doc**: Core Application Infrastructure

핵심 인프라 모듈:
- config: 설정 관리
- logging: 로깅 시스템
- errors: 예외 정의...
- **Coverage**: 0.0% (0/3 lines)

### app/core/errors.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/34 lines)

### app/core/logging.py [🔗 REACHABLE]
- **Lines of Code**: 104
- **Module Doc**: 통합 로깅 시스템

모든 모듈은 이 모듈의 get_logger()를 사용합니다.

Example:
    >>> from app.core.logging import get_logg...
- **Functions**:
  - `_init_logger(...)`
  - `get_logger(name...)`
  - `set_level(level...)`
- **Coverage**: 0.0% (0/37 lines)

### app/rag/__init__.py [❌ UNUSED]
- **Lines of Code**: 15
- **Module Doc**: RAG (Retrieval-Augmented Generation) Module

핵심 컴포넌트:
- pipeline: RAG 파사드 (단일 진입점)
- metrics: 성능 지표 ...
- **Coverage**: 0.0% (0/2 lines)

### app/rag/parse/__init__.py [❌ UNUSED]
- **Lines of Code**: 6
- **Module Doc**: RAG 파싱 모듈...
- **Coverage**: 0.0% (0/3 lines)

### app/rag/parse/doctype.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/63 lines)

### app/rag/parse/parse_meta.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/149 lines)

### app/rag/parse/parse_tables.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/127 lines)

### app/rag/pipeline.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/692 lines)

### app/rag/preprocess/__init__.py [❌ UNUSED]
- **Lines of Code**: 5
- **Module Doc**: RAG 전처리 모듈...
- **Coverage**: 0.0% (0/2 lines)

### app/rag/preprocess/clean_text.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/126 lines)

### app/rag/query_parser.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/98 lines)

### app/rag/query_router.py [❌ UNUSED]
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
- **Coverage**: 0.0% (0/119 lines)

### app/rag/render/__init__.py [❌ UNUSED]
- **Lines of Code**: 5
- **Module Doc**: RAG 렌더링 모듈...
- **Coverage**: 0.0% (0/2 lines)

### app/rag/render/list_postprocess.py [❌ UNUSED]
- **Lines of Code**: 133
- **Module Doc**: 검색 결과 목록 후처리 모듈
- 텍스트 노이즈 제거 (타임스탬프, URL, 페이지 번호)
- 중복 문서 제거 (정규화된 파일명 기준)
- 빈 스니펫 폴백 (메타데이터 기반)...
- **Functions**:
  - `_normalize_fname(name...)`
  - `_parse_date(s...)`
  - `_clean_snippet(text...)`
  - `_fallback_snippet(item...)`
  - `_primary_snippet(item...)`
- **Coverage**: 0.0% (0/72 lines)

### app/rag/render/summary_templates.py [❌ UNUSED]
- **Lines of Code**: 396
- **Module Doc**: 요약 템플릿 렌더링 모듈
2025-10-26

문서 요약을 고정된 4섹션 구조로 렌더링합니다.

구조:
1. 핵심 요약: 장애 요지, 조치, 리스크
2. 비용 (VAT 별도): 항...
- **Classes**:
  - `SummaryRenderer` (12 methods)
- **Functions**:
  - `__init__(self, config_path...)`
  - `_load_config(self, config_path...)`
  - `render(self, filename, meta...)`
  - `_render_proposal(self, filename, meta...)`
  - `_render_report(self, filename, meta...)`
- **Coverage**: 0.0% (0/155 lines)

### app/rag/retrievers/__init__.py [❌ UNUSED]
- **Lines of Code**: 15
- **Module Doc**: 검색 엔진 모듈

구현체:
- hybrid: 하이브리드 검색 (BM25 + Dense) - QuickFixRAG 래퍼
- bm25: BM25 검색 (TODO)
- dense: De...
- **Coverage**: 0.0% (0/2 lines)

### app/rag/retrievers/hybrid.py [❌ UNUSED]
- **Lines of Code**: 93
- **Module Doc**: 하이브리드 검색 엔진 (MetadataDB 기반 임시 구현)

QuickFixRAG가 제거되어 MetadataDB를 사용한 간단한 검색으로 대체...
- **Classes**:
  - `HybridRetriever` (2 methods)
- **Functions**:
  - `__init__(self...)`
  - `search(self, query, top_k...)`
- **Coverage**: 0.0% (0/34 lines)

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

### app/rag/utils/context_hydrator.py [❌ UNUSED]
- **Lines of Code**: 157
- **Module Doc**: Context Hydrator - 청크에서 텍스트 추출 및 PDF 보강...
- **Functions**:
  - `hydrate_context(chunks, max_len...)`
  - `_extract_text_from_chunk(chunk, metrics...)`
  - `_extract_pdf_tail(chunk, metrics, needed...)`
- **Coverage**: 0.0% (0/76 lines)

### app/rag/utils/json_utils.py [❌ UNUSED]
- **Lines of Code**: 206
- **Module Doc**: JSON 파싱 유틸리티 (강건한 파서)...
- **Functions**:
  - `extract_last_json_block(s...)`
  - `parse_summary_json_robust(response...)`
  - `ensure_citations(json_data, doc_ref...)`
  - `extract_amounts_from_text(text...)`
  - `validate_numeric_fields(json_data, source_text...)`
- **Coverage**: 0.0% (0/95 lines)

### modules/cache_module.py [❌ UNUSED]
- **Lines of Code**: 371
- **Module Doc**: from app.core.logging import get_logger
캐시 관리 모듈 - Perfect RAG에서 분리된 캐시 관련 기능
2025-09-29 리팩토링

이 모듈은...
- **Classes**:
  - `CacheModule` (20 methods)
- **Functions**:
  - `__init__(self, config...)`
  - `manage_cache(self, cache_dict, key...)`
  - `get_from_cache(self, cache_dict, key...)`
  - `set_document_cache(self, key, value...)`
  - `get_document_cache(self, key...)`
- **Coverage**: 0.0% (0/160 lines)

### modules/document_module.py [❌ UNUSED]
- **Lines of Code**: 418
- **Module Doc**: from app.core.logging import get_logger
문서 처리 모듈 - Perfect RAG에서 분리된 문서 처리 기능
2025-09-29 리팩토링

이 모듈은...
- **Classes**:
  - `DocumentModule` (11 methods)
- **Functions**:
  - `__init__(self, config...)`
  - `extract_pdf_text(self, pdf_path, use_cache...)`
  - `extract_pdf_text_with_retry(self, pdf_path, max_retries...)`
  - `extract_txt_content(self, txt_path...)`
  - `process_documents_parallel(self, file_paths, process_func...)`
- **Coverage**: 0.0% (0/219 lines)

### modules/intent_module.py [❌ UNUSED]
- **Lines of Code**: 337
- **Module Doc**: from app.core.logging import get_logger
Intent Module - 사용자 의도 분석 및 분류 시스템
사용자의 질문 의도를 분석하고 적절한 응답 스...
- **Classes**:
  - `IntentModule` (8 methods)
- **Functions**:
  - `__init__(self, llm_module...)`
  - `analyze_user_intent(self, query...)`
  - `classify_search_intent(self, query...)`
  - `generate_conversational_response(self, context, query...)`
  - `_generate_llm_response(self, context, query...)`
- **Coverage**: 0.0% (0/109 lines)

### modules/llm_module.py [❌ UNUSED]
- **Lines of Code**: 401
- **Module Doc**: from app.core.logging import get_logger
LLM 처리 모듈 - Perfect RAG에서 분리된 LLM 관련 기능
2025-09-29 리팩토링

이 모...
- **Classes**:
  - `LLMModule` (15 methods)
- **Functions**:
  - `__init__(self, config...)`
  - `_init_prompts(self...)`
  - `load_llm(self...)`
  - `generate_response(self, context, query...)`
  - `generate_smart_summary(self, text, title...)`
- **Coverage**: 0.0% (0/133 lines)

### modules/metadata_db.py [🔗 REACHABLE]
- **Lines of Code**: 747
- **Module Doc**: Phase 1.2: 메타데이터 DB 구축
SQLite를 사용한 PDF 메타데이터 관리...
- **Classes**:
  - `MetadataDB` (27 methods)
- **Functions**:
  - `extract_metadata_from_filename(filename...)`
  - `__init__(self, db_path...)`
  - `init_database(self...)`
  - `_migrate_schema(self...)`
  - `add_document(self, metadata...)`
- **Coverage**: 0.0% (0/300 lines)

### modules/metadata_extractor.py [🔗 REACHABLE]
- **Lines of Code**: 524
- **Module Doc**: 고급 메타데이터 추출기 - PDF에서 구조화된 정보 추출...
- **Entry Point**: Yes ⚡
- **Classes**:
  - `MetadataExtractor` (14 methods)
- **Functions**:
  - `test_extractor(...)`
  - `__init__(self...)`
  - `extract_all(self, text, filename...)`
  - `_normalize_text(self, text...)`
  - `_extract_dates(self, text...)`
- **Coverage**: 0.0% (0/201 lines)

### modules/ocr_processor.py [🔗 REACHABLE]
- **Lines of Code**: 350
- **Module Doc**: from app.core.logging import get_logger
OCR 처리 모듈 - 스캔된 PDF 문서를 텍스트로 변환...
- **Entry Point**: Yes ⚡
- **Classes**:
  - `OCRProcessor` (11 methods)
- **Functions**:
  - `test_ocr(...)`
  - `__init__(self, cache_dir...)`
  - `_init_db(self...)`
  - `_get_file_hash(self, file_path...)`
  - `_check_cache(self, file_hash...)`
- **Coverage**: 0.0% (0/154 lines)

### modules/optimized_llm.py [❌ UNUSED]
- **Lines of Code**: 33
- **Classes**:
  - `OptimizedLLMModule` (2 methods)
- **Functions**:
  - `__init__(self...)`
  - `generate_optimized(self, query, context...)`
- **Coverage**: 0.0% (0/18 lines)

### modules/reranker.py [❌ UNUSED]
- **Lines of Code**: 300
- **Module Doc**: 리랭커 모듈 - L2 RAG 완성을 위한 규칙 기반 리랭커
2025-10-25 생성

검색 결과를 다음 기준으로 재정렬:
1. 제목 정확 매치: 쿼리 키워드가 filename에 정...
- **Classes**:
  - `RuleBasedReranker` (8 methods)
- **Functions**:
  - `rerank_search_results(query, results, top_k...)`
  - `__init__(self, config...)`
  - `rerank(self, query, results...)`
  - `_extract_keywords(self, query...)`
  - `_extract_category_keywords(self, query...)`
- **Coverage**: 0.0% (0/104 lines)

### modules/response_formatter.py [🔗 REACHABLE]
- **Lines of Code**: 957
- **Module Doc**: from app.core.logging import get_logger
고급 응답 포맷터 시스템

주요 기능:
- 템플릿 기반 포맷팅
- 다중 출력 형식 지원 (Plain, Mar...
- **Entry Point**: Yes ⚡
- **Classes**:
  - `FormatType` 
  - `ThemeStyle` 
  - `FormatConfig` 
  - `Template` (3 methods)
  - `I18n` (1 methods)
- **Functions**:
  - `create_formatter(format_type, theme, language...)`
  - `format_as_markdown(data, formatter_type...)`
  - `format_as_html(data, formatter_type...)`
  - `__init__(self, template_str...)`
  - `_compile(self, template_str...)`
- **Coverage**: 0.0% (0/452 lines)

### modules/search_module.py [🔗 REACHABLE]
- **Lines of Code**: 434
- **Module Doc**: 검색 모듈 - Perfect RAG에서 분리된 검색 기능
2025-09-29 리팩토링

이 모듈은 perfect_rag.py에서 검색 관련 기능을 분리하여
유지보수성과 가독성을 높...
- **Classes**:
  - `SearchModule` (16 methods)
- **Functions**:
  - `__init__(self, docs_dir, config...)`
  - `search_by_drafter(self, drafter_name, top_k...)`
  - `search_by_content(self, query, top_k...)`
  - `_legacy_search(self, query, top_k...)`
  - `_parallel_search_pdfs(self, pdf_files, query...)`
- **Coverage**: 0.0% (0/235 lines)

### modules/search_module_hybrid.py [🔗 REACHABLE]
- **Lines of Code**: 249
- **Module Doc**: 하이브리드 검색 모듈 - BM25 + Vector 검색 통합
SearchModule을 확장하여 하이브리드 검색 기능 추가...
- **Entry Point**: Yes ⚡
- **Classes**:
  - `SearchModuleHybrid` (6 methods)
- **Functions**:
  - `test_hybrid_search(...)`
  - `__init__(self, docs_dir, config...)`
  - `_init_hybrid_search(self...)`
  - `search_by_content(self, query, top_k...)`
  - `_determine_search_mode(self, query...)`
- **Coverage**: 0.0% (0/98 lines)

### modules/statistics_module.py [❌ UNUSED]
- **Lines of Code**: 569
- **Module Doc**: from app.core.logging import get_logger
통계 및 리포트 모듈 - Perfect RAG에서 분리된 통계/분석 기능
2025-09-29 리팩토링

이 ...
- **Classes**:
  - `StatisticsModule` (15 methods)
- **Functions**:
  - `__init__(self, config...)`
  - `collect_statistics_data(self, query, metadata_cache...)`
  - `_collect_yearly_purchase_stats(self, metadata_cache, target_year...)`
  - `_collect_drafter_stats(self, metadata_cache, target_year...)`
  - `_collect_monthly_repair_stats(self, metadata_cache, target_year...)`
- **Coverage**: 0.0% (0/264 lines)
