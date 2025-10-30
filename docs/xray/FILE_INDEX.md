# File Index - RAG System X-Ray
Generated: 2025-10-30 12:39:30

## Classification Legend
- **USED**: File has runtime coverage (executed during tests)
- **REACHABLE**: File is imported/reachable from entry points
- **UNUSED**: File has no coverage and is not reachable

## Directory Tree with Classifications
```
app/
  api/
    __init__.py [❌ UNUSED]
    main.py [🔗 REACHABLE]
  config/
    __init__.py [❌ UNUSED]
    settings.py [❌ UNUSED]
  core/
    __init__.py [❌ UNUSED]
    errors.py [❌ UNUSED]
    logging.py [🔗 REACHABLE]
  rag/
    parse/
      __init__.py [❌ UNUSED]
      doctype.py [❌ UNUSED]
      parse_meta.py [❌ UNUSED]
      parse_tables.py [❌ UNUSED]
    preprocess/
      __init__.py [❌ UNUSED]
      clean_text.py [❌ UNUSED]
    render/
      __init__.py [❌ UNUSED]
      list_postprocess.py [❌ UNUSED]
      summary_templates.py [❌ UNUSED]
    retrievers/
      __init__.py [❌ UNUSED]
      hybrid.py [❌ UNUSED]
    utils/
      __init__.py [❌ UNUSED]
      context_hydrator.py [❌ UNUSED]
      json_utils.py [❌ UNUSED]
    __init__.py [❌ UNUSED]
    pipeline.py [❌ UNUSED]
    query_parser.py [❌ UNUSED]
    query_router.py [❌ UNUSED]
    summary_templates.py [❌ UNUSED]
  __init__.py [❌ UNUSED]
modules/
  cache_module.py [❌ UNUSED]
  document_module.py [❌ UNUSED]
  intent_module.py [❌ UNUSED]
  llm_module.py [❌ UNUSED]
  metadata_db.py [🔗 REACHABLE]
  metadata_extractor.py [🔗 REACHABLE]
  ocr_processor.py [🔗 REACHABLE]
  optimized_llm.py [❌ UNUSED]
  reranker.py [❌ UNUSED]
  response_formatter.py [🔗 REACHABLE]
  search_module.py [🔗 REACHABLE]
  search_module_hybrid.py [🔗 REACHABLE]
  statistics_module.py [❌ UNUSED]
```

## Summary Statistics
- **Total Python files**: 40
- **USED (with coverage)**: 0 (0.0%)
- **REACHABLE (no coverage)**: 8 (20.0%)
- **UNUSED**: 32 (80.0%)