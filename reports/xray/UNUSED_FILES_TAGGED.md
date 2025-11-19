# 미사용 파일 태깅 (66개)

**Date**: 2025-11-14
**Source**: `reports/USAGE_AUDIT.md` (휴리스틱 분석 결과)
**Purpose**: 안전한 아카이브/삭제를 위한 수동 검토 및 카테고리 분류

---

## 분류 기준

- **FALSE_POSITIVE**: 실제로 사용 중이나 휴리스틱 오탐 (절대 삭제 금지)
- **LEGACY**: 과거 코드, 보존 필요 (modules_legacy/ 또는 archive/로 이동)
- **SAFE_DELETE**: 안전하게 삭제 가능 (중복/실험용 코드)
- **NEEDS_REVIEW**: 추가 검토 필요 (실제 import 재확인)

---

## 1. FALSE_POSITIVE (실제 사용 중) - 7개

**절대 삭제 금지**. 이전 X-Ray 분석에서 실제 사용 확인된 파일.

| File | 사용처 | 비고 |
|------|--------|------|
| `app/rag/summary_templates.py` | `app/rag/pipeline.py:import summary_templates` | 동적 import로 rg 탐지 실패 |
| `app/rag/pipeline.py` | 핵심 RAG 파이프라인 | 실제 운영 코드 |
| `components/pdf_viewer.py` | Streamlit UI 컴포넌트 | web_interface.py에서 사용 |
| `app/config/compat.py` | 하위 호환성 레이어 | 설정 마이그레이션용 |
| `app/config/performance_compat.py` | 성능 설정 호환성 | 설정 마이그레이션용 |
| `app/core/errors.py` | 커스텀 예외 정의 | try/except로 사용, import 미탐지 |
| `app/rag/cache_manager.py` | 캐시 관리 인터페이스 | 동적 로딩 가능성 |

**조치**: 이 파일들은 USAGE_AUDIT에서 제외하거나 "USED (dynamic import)" 태그 추가 필요.

---

## 2. LEGACY (보존 필요) - 25개

**삭제 금지, modules_legacy/ 또는 archive/YYYY-MM-DD/로 이동**.

### 2.1 Legacy Modules (2개)
| File | 비고 |
|------|------|
| `modules_legacy/metadata_extractor.py` | 이미 modules_legacy/에 있음, 보존 |
| `modules_legacy/search_module.py` | 이미 modules_legacy/에 있음, 보존 |

### 2.2 Legacy Tests (23개)
**과거 테스트 코드, pytest에서 실행되지 않지만 참고용으로 보존**.

| File | 비고 |
|------|------|
| `tests/rag/parse/test_parse_meta_extended.py` | parse_meta 확장 테스트 (v0.9) |
| `tests/rag/parse/test_parse_tables_extended.py` | parse_tables 확장 테스트 (v0.9) |
| `tests/test_alerts.py` | alerts.py 테스트 (현재 미사용) |
| `tests/test_amount_parser_v2.py` | 금액 파서 v2 테스트 (v1로 통합됨) |
| `tests/test_claimed_total.py` | 청구 금액 합계 테스트 (v0.8) |
| `tests/test_clean_text.py` | 텍스트 정제 테스트 (v0.9) |
| `tests/test_config_schema_v1.py` | 설정 스키마 v1 테스트 (v2로 업그레이드) |
| `tests/test_context_hydrator.py` | 컨텍스트 hydrator 테스트 |
| `tests/test_e2e_app.py` | E2E 앱 테스트 (deprecated) |
| `tests/test_exact_match_contract.py` | Exact match 계약 테스트 |
| `tests/test_filename_matching.py` | 파일명 매칭 테스트 |
| `tests/test_ingest_from_docs.py` | 문서 인제스트 테스트 |
| `tests/test_json_utils.py` | JSON 유틸 테스트 |
| `tests/test_normalizer.py` | Normalizer 테스트 |
| `tests/test_parse_meta.py` | parse_meta 기본 테스트 |
| `tests/test_parse_table.py` | parse_table 기본 테스트 |
| `tests/test_performance_config_v1.py` | 성능 설정 v1 테스트 |
| `tests/test_query_filters_v1.py` | 쿼리 필터 v1 테스트 |
| `tests/test_results_list_postprocess.py` | 결과 후처리 테스트 |
| `tests/test_router_profiles_v1.py` | 라우터 프로필 v1 테스트 |
| `tests/test_sqlite_helpers.py` | SQLite 헬퍼 테스트 |
| `tests/test_text_normalizer.py` | 텍스트 normalizer 테스트 |
| `tests/test_validation_report.py` | 검증 리포트 테스트 |

**이동 계획**:
```bash
# 테스트는 archive/legacy_tests/로 이동 (삭제 X)
mkdir -p archive/legacy_tests/rag/parse
mv tests/test_*.py archive/legacy_tests/ 2>/dev/null || true
mv tests/rag/parse/test_*_extended.py archive/legacy_tests/rag/parse/ 2>/dev/null || true
```

---

## 3. SAFE_DELETE (안전 삭제 가능) - 11개

**실험용/중복/deprecated 코드로 삭제 가능**.

### 3.1 Utilities (9개)
| File | 이유 |
|------|------|
| `utils/css_loader.py` | Streamlit CSS 로더 (components/에 통합됨) |
| `utils/document_loader.py` | 문서 로더 (app/rag/에 통합됨) |
| `utils/error_handler.py` | 에러 핸들러 (app/core/errors.py로 이동) |
| `utils/path_validator.py` | 경로 검증 (pathlib로 대체) |
| `utils/pdf_utils.py` | PDF 유틸 (app/rag/parse/로 통합) |
| `utils/performance.py` | 성능 측정 (app/config/performance.py로 이동) |
| `utils/session_manager.py` | 세션 관리 (Streamlit 내장 사용) |
| `utils/streaming.py` | 스트리밍 (FastAPI StreamingResponse 사용) |
| `utils/year_utils.py` | 연도 유틸 (app/utils/date_utils.py로 통합) |

### 3.2 Scripts (1개)
| File | 이유 |
|------|------|
| `scripts/verify_env_integrity.py` | 환경 검증 (audit_repo.sh로 대체) |

### 3.3 RAG System (1개)
| File | 이유 |
|------|------|
| `rag_system/active/enhanced_ocr_processor.py` | 향상된 OCR (app/rag/parse/로 통합) |

**삭제 계획**:
```bash
# archive/2025-11-14/로 이동 후 검증 기간 1개월 후 삭제
python scripts/apply_archive.py reports/xray/safe_delete_candidates.txt
```

---

## 4. NEEDS_REVIEW (추가 검토 필요) - 23개

**실제 import 재확인 후 판단**.

### 4.1 App Core (4개)
| File | 검토 항목 |
|------|----------|
| `app/alerts.py` | FastAPI 알림 시스템 사용 여부 |
| `app/extractors/device_fields.py` | 장비 필드 추출 사용 여부 |
| `app/extractors/finance.py` | 금액 추출 사용 여부 (amount_parser.py와 중복?) |
| `app/extractors/merge.py` | 추출 결과 병합 사용 여부 |

### 4.2 App Index (1개)
| File | 검토 항목 |
|------|----------|
| `app/index/bm25_store.py` | BM25 저장소 (index_bm25.py와 중복?) |

### 4.3 App Prompts (1개)
| File | 검토 항목 |
|------|----------|
| `app/prompts/document_prompts.py` | 문서 프롬프트 템플릿 사용 여부 |

### 4.4 App Query (1개)
| File | 검토 항목 |
|------|----------|
| `app/query/filters.py` | 쿼리 필터 사용 여부 (query_optimizer.py와 중복?) |

### 4.5 App RAG (11개)
| File | 검토 항목 |
|------|----------|
| `app/rag/cache_namespace.py` | 캐시 네임스페이스 (smart_cache_key.py와 중복?) |
| `app/rag/parse/doctype.py` | 문서 타입 분류 사용 여부 |
| `app/rag/parse/parse_meta.py` | 메타데이터 파싱 (실제 사용 중일 가능성) |
| `app/rag/parse/parse_tables.py` | 테이블 파싱 (실제 사용 중일 가능성) |
| `app/rag/persistent_cache.py` | 영구 캐시 (smart_cache_key.py와 중복?) |
| `app/rag/preprocess/clean_text.py` | 텍스트 정제 (실제 사용 중일 가능성) |
| `app/rag/query_parser.py` | 쿼리 파서 (query_optimizer.py와 중복?) |
| `app/rag/query_router.py` | 쿼리 라우터 (routing/*.py와 중복?) |
| `app/rag/retrievers/exact_match.py` | Exact match retriever (실제 사용 중일 가능성) |
| `app/rag/retrievers/hybrid.py` | Hybrid retriever (실제 사용 중일 가능성) |
| `app/rag/routing_monitor.py` | 라우팅 모니터링 사용 여부 |

### 4.6 App Utils (2개)
| File | 검토 항목 |
|------|----------|
| `app/rag/utils/context_hydrator.py` | 컨텍스트 hydrator 사용 여부 |
| `app/rag/utils/json_utils.py` | JSON 유틸 사용 여부 |
| `app/utils/sqlite_helpers.py` | SQLite 헬퍼 사용 여부 (metadata_db.py와 중복?) |
| `app/utils/text_normalizer.py` | 텍스트 normalizer (textproc/normalizer.py와 중복?) |

### 4.7 RAG System (1개)
| File | 검토 항목 |
|------|----------|
| `rag_system/active/llm_singleton.py` | LLM 싱글톤 사용 여부 (app/rag/llm.py와 중복?) |

**검토 방법**:
```bash
# 각 파일에 대해 실제 import 확인
for file in app/alerts.py app/extractors/device_fields.py ...; do
    echo "=== $file ==="
    rg "import.*$(basename $file .py)" --type py
    rg "from.*$(basename $file .py)" --type py
done

# 또는 Python AST 파싱으로 동적 import 탐지
python scripts/detect_dynamic_imports.py
```

---

## 5. 태깅 요약

| 카테고리 | 개수 | 조치 |
|----------|------|------|
| FALSE_POSITIVE | 7 | 절대 보존 (오탐) |
| LEGACY | 25 | modules_legacy/ or archive/legacy_tests/ 이동 |
| SAFE_DELETE | 11 | archive/2025-11-14/ 이동 후 1개월 검증 기간 |
| NEEDS_REVIEW | 23 | 실제 import 재확인 후 재분류 |
| **Total** | **66** | |

---

## 6. 다음 단계

### 6.1 즉시 실행 가능
```bash
# SAFE_DELETE 11개 아카이브 (삭제 X)
cat > reports/xray/safe_delete_candidates.txt <<EOF
utils/css_loader.py
utils/document_loader.py
utils/error_handler.py
utils/path_validator.py
utils/pdf_utils.py
utils/performance.py
utils/session_manager.py
utils/streaming.py
utils/year_utils.py
scripts/verify_env_integrity.py
rag_system/active/enhanced_ocr_processor.py
EOF

python scripts/apply_archive.py reports/xray/safe_delete_candidates.txt
```

### 6.2 수동 검토 필요
```bash
# NEEDS_REVIEW 23개에 대해 실제 사용 여부 확인
bash scripts/verify_actual_usage.sh reports/xray/needs_review_list.txt
```

### 6.3 보류 (FALSE_POSITIVE)
```bash
# 7개는 절대 삭제/이동 금지
# USAGE_AUDIT.md 업데이트 시 제외 리스트에 추가
```

---

## 7. 참고

- **휴리스틱 한계**: `rg "import.*filename"` 패턴으로만 탐지하므로 동적 import 미탐지
- **오탐 사례**: `summary_templates.py`, `pipeline.py`, `pdf_viewer.py` 등
- **안전 우선**: 의심스러우면 LEGACY로 분류 후 보존

**이 태깅은 v1.0.0 기준이며, 실제 정리 전 반드시 import 재확인 필요합니다.**
