# File Index - RAG System X-Ray
Generated: 2025-11-14 11:19:37

## Classification Legend
- **USED**: File has runtime coverage (executed during tests)
- **REACHABLE**: File is imported/reachable from entry points
- **UNUSED**: File has no coverage and is not reachable

## Directory Tree with Classifications
```
app/
  api/
    __init__.py [❌ UNUSED]
    main.py [✅ USED]
  config/
    __init__.py [❌ UNUSED]
    compat.py [❌ UNUSED]
    performance_compat.py [❌ UNUSED]
    settings.py [✅ USED]
  core/
    __init__.py [✅ USED]
    errors.py [✅ USED]
    logging.py [✅ USED]
  data/
    __init__.py [❌ UNUSED]
    amount_parser_v2.py [🔗 REACHABLE]
    metadata_db.py [❌ UNUSED]
  extractors/
    __init__.py [❌ UNUSED]
    device_fields.py [❌ UNUSED]
    finance.py [❌ UNUSED]
    merge.py [❌ UNUSED]
  index/
    __init__.py [❌ UNUSED]
    bm25_store.py [❌ UNUSED]
  logging/
    config.py [🔗 REACHABLE]
  prompts/
    document_prompts.py [❌ UNUSED]
  query/
    __init__.py [❌ UNUSED]
    filters.py [❌ UNUSED]
  rag/
    parse/
      __init__.py [✅ USED]
      doctype.py [✅ USED]
      parse_meta.py [✅ USED]
      parse_tables.py [✅ USED]
    preprocess/
      __init__.py [✅ USED]
      clean_text.py [✅ USED]
    retrievers/
      __init__.py [✅ USED]
      exact_match.py [❌ UNUSED]
      hybrid.py [✅ USED]
    routing/
      __init__.py [❌ UNUSED]
      anchor_scorer.py [❌ UNUSED]
      profile_matcher.py [❌ UNUSED]
    utils/
      __init__.py [❌ UNUSED]
      context_hydrator.py [✅ USED]
      json_utils.py [✅ USED]
    __init__.py [✅ USED]
    cache_manager.py [❌ UNUSED]
    cache_namespace.py [❌ UNUSED]
    metrics_collector.py [🔗 REACHABLE]
    parallel_executor.py [❌ UNUSED]
    persistent_cache.py [❌ UNUSED]
    pipeline.py [✅ USED]
    query_expander.py [❌ UNUSED]
    query_parser.py [✅ USED]
    query_router.py [✅ USED]
    routing_monitor.py [❌ UNUSED]
    smart_cache_key.py [🔗 REACHABLE]
    summary_templates.py [❌ UNUSED]
  textproc/
    normalizer.py [🔗 REACHABLE]
  utils/
    sqlite_helpers.py [❌ UNUSED]
    text_normalizer.py [❌ UNUSED]
  __init__.py [✅ USED]
  alerts.py [🔗 REACHABLE]
```

## Summary Statistics
- **Total Python files**: 55
- **USED (with coverage)**: 20 (36.4%)
- **REACHABLE (no coverage)**: 6 (10.9%)
- **UNUSED**: 29 (52.7%)