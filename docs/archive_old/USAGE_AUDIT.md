# Usage Audit Report

**Date**: 2025-11-14 15:00:56

**Project Root**: `/home/wnstn4647/AI-CHAT`

**Total Files**: 198
**Used**: 132
**Unused (suspected)**: 66

## Unused Files (suspected)

| File | Status | Reason |
|------|--------|--------|
| `app/alerts.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/config/compat.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/config/performance_compat.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/core/errors.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/extractors/device_fields.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/extractors/finance.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/extractors/merge.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/index/bm25_store.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/prompts/document_prompts.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/query/filters.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/cache_manager.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/cache_namespace.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/parse/doctype.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/parse/parse_meta.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/parse/parse_tables.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/persistent_cache.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/pipeline.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/preprocess/clean_text.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/query_parser.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/query_router.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/retrievers/exact_match.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/retrievers/hybrid.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/routing_monitor.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/summary_templates.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/utils/context_hydrator.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/rag/utils/json_utils.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/utils/sqlite_helpers.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `app/utils/text_normalizer.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `components/pdf_viewer.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `modules_legacy/metadata_extractor.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `modules_legacy/search_module.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `rag_system/active/enhanced_ocr_processor.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `rag_system/active/llm_singleton.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `scripts/verify_env_integrity.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/rag/parse/test_parse_meta_extended.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/rag/parse/test_parse_tables_extended.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_alerts.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_amount_parser_v2.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_claimed_total.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_clean_text.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_config_schema_v1.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_context_hydrator.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_e2e_app.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_exact_match_contract.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_filename_matching.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_ingest_from_docs.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_json_utils.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_normalizer.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_parse_meta.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_parse_table.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_performance_config_v1.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_query_filters_v1.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_results_list_postprocess.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_router_profiles_v1.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_sqlite_helpers.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_text_normalizer.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `tests/test_validation_report.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/css_loader.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/document_loader.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/error_handler.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/path_validator.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/pdf_utils.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/performance.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/session_manager.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/streaming.py` | UNUSED | No imports (rg=True), not CLI, not special |
| `utils/year_utils.py` | UNUSED | No imports (rg=True), not CLI, not special |

## Used Files (top 20 by import count)

| File | Imports | CLI | Special |
|------|---------|-----|---------|
| `app/core/logging.py` | 24 |  |  |
| `app/logging/config.py` | 7 |  |  |
| `app/config/settings.py` | 6 |  |  |
| `app/rag/smart_cache_key.py` | 2 | ✓ |  |
| `components/chat_interface.py` | 2 |  |  |
| `components/document_preview.py` | 2 |  |  |
| `components/sidebar_library.py` | 2 |  |  |
| `config/indexing.py` | 2 |  |  |
| `app/__init__.py` | 1 |  | ✓ |
| `app/api/__init__.py` | 1 |  | ✓ |
| `app/api/main.py` | 1 | ✓ |  |
| `app/config/__init__.py` | 1 |  | ✓ |
| `app/core/__init__.py` | 1 |  | ✓ |
| `app/data/__init__.py` | 1 |  | ✓ |
| `app/data/metadata_db.py` | 1 |  |  |
| `app/extractors/__init__.py` | 1 |  | ✓ |
| `app/index/__init__.py` | 1 |  | ✓ |
| `app/query/__init__.py` | 1 |  | ✓ |
| `app/rag/__init__.py` | 1 |  | ✓ |
| `app/rag/metrics_collector.py` | 1 |  |  |
