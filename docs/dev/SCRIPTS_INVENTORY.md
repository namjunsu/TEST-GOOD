# scripts/ 인벤토리

**작성일**: 2025-11-24
**목적**: 스크립트 정리(필수/보조/deprecated) 및 중복 기능 파악
**상태**: 초안 (59개 스크립트 중 일부만 분류 완료)

---

## 분류 기준

### Category
- **core**: 운영에 필수 (서비스 중단과 직접 연결)
- **ops**: 운영 보조/진단/헬스체크
- **tool**: 1회성/실험/마이그레이션용
- **deprecated**: 더 이상 사용하지 않음 (호환성만 유지)

### Status
- **active**: 현재 사용 중
- **candidate_deprecate**: 사용 빈도 낮음, 통합/폐기 후보
- **deprecated**: 사용 중지, 제거 예정

---

## 핵심 스크립트 (운영 필수)

| 이름 | Category | Status | 역할/설명 | 호출 경로/사용처 | 비고 |
|------|----------|--------|-----------|------------------|------|
| **ingest_from_docs.py** | core | active | docs/incoming → 메타DB/인덱싱 | 수동 실행, 신규 문서 처리 | **통합 기준 스크립트** |
| **reindex_atomic.py** | core | active | 부분/전체 BM25 재인덱싱 | 수동/cron | 문서 추가 후 필수 |
| **healthcheck.py** | ops | active | 시스템 전체 상태 체크 | 수동/cron (매일) | 2025-11-24 신규 추가 |
| **auto_sync_checker.py** | ops | active | 파일-DB 동기화 확인 및 복구 | 수동/cron (주 1회) | 2025-11-24 신규 추가 |
| **cleanup_duplicates.py** | ops | active | 중복 파일 정리 | 수동/cron (월 1회) | 2025-11-24 신규 추가 |
| **backup_db.py** | ops | active | DB 자동 백업 | cron (매일 02:00) | 2025-11-24 신규 추가 |

---

## 중복 기능 스크립트 그룹

### 1. 인제스트 관련 (통합 필요)
| 이름 | Status | 비고 |
|------|--------|------|
| ingest_from_docs.py | active | ✅ **기준 스크립트** |
| ingest_content.py | candidate_deprecate | 기능 중복, 통합 검토 필요 |
| ingest_dryrun.py | tool | dry-run 옵션으로 통합 가능 |

### 2. OCR 재처리 (통합 필요)
| 이름 | Status | 비고 |
|------|--------|------|
| force_ocr_update.py | active | ✅ **기준 스크립트** |
| reprocess_with_ocr.py | candidate_deprecate | 기능 중복 |
| reprocess_poor_docs_with_ocr.py | candidate_deprecate | 기능 중복 |
| batch_ocr_zero_chars.py | candidate_deprecate | force_ocr_update.py로 통합 가능 |
| batch_ocr_from_report.py | tool | 1회성 마이그레이션용 |

### 3. 텍스트 품질 개선 (통합 필요)
| 이름 | Status | 비고 |
|------|--------|------|
| improve_text_quality.py | candidate_deprecate | 구버전 |
| improve_text_quality_simple.py | candidate_deprecate | 단순 버전, 통합 검토 |

### 4. 인덱스 재구축
| 이름 | Status | 비고 |
|------|--------|------|
| reindex_atomic.py | active | ✅ **기준 스크립트** |
| quick_rebuild_bm25.py | candidate_deprecate | reindex_atomic.py로 통합 가능 |
| rebuild_rag_indexes.py | deprecated | 사용 중지 |

### 5. 메타데이터 재추출
| 이름 | Status | 비고 |
|------|--------|------|
| reextract_metadata.py | active | ✅ **기준 스크립트** (2025-11-24) |
| reextract_specific_pdf.py | tool | 1회성 디버깅용 |

---

## 진단/검증 스크립트

| 이름 | Category | Status | 역할 |
|------|----------|--------|------|
| smoke_test.py | ops | active | 기본 기능 헬스체크 |
| check_fs_vs_db.py | ops | candidate_deprecate | auto_sync_checker.py와 중복 |
| validate_metadata.py | ops | active | 메타데이터 품질 검증 |
| validate_rag.py | ops | active | RAG 파이프라인 검증 |
| db_verify.py | ops | active | DB 무결성 체크 |
| db_dedupe.py | tool | active | DB 중복 제거 |

---

## 분석/실험 스크립트 (tool)

| 이름 | Status | 역할 |
|------|--------|------|
| audit_usage.py | active | 사용량 분석 |
| analyze_usage.py | candidate_deprecate | audit_usage.py와 중복? |
| audit_missing_content.py | active | 누락 콘텐츠 분석 |
| scan_poor_extraction.py | active | OCR 품질 낮은 문서 스캔 |
| anomaly_detector.py | tool | 이상 탐지 (실험용) |
| bench_rag.py | tool | RAG 성능 벤치마크 |
| benchmark_context_hydrator.py | tool | 컨텍스트 하이드레이터 벤치마크 |

---

## 유틸리티/1회성 스크립트

| 이름 | Status | 역할 |
|------|--------|------|
| create_ppt.py | tool | PPT 생성 |
| list_documents.py | tool | 문서 목록 출력 |
| extract_full_text.py | tool | 전체 텍스트 추출 |
| clean_extracted_texts.py | tool | 추출 텍스트 정리 |
| verify_env_integrity.py | ops | 환경 설정 검증 |
| verify_imports.py | ops | import 검증 |
| verify_exact_match_indexes.py | ops | 인덱스 정합성 검증 |

---

## 코드 분석/생성 (개발용)

| 이름 | Status | 역할 |
|------|--------|------|
| build_codemap.py | tool | 코드맵 생성 |
| xray_corrected.py | tool | 코드 분석 |
| xray_used_unused.py | tool | 사용/미사용 코드 분석 |
| generate_code_tests.py | tool | 테스트 코드 생성 |
| dot_to_svg_html.py | tool | DOT → SVG/HTML 변환 |

---

## 미분류 스크립트 (다음 세션에서 분류)

- generate_askable_queries.py
- validate_askable_queries.py
- scenario_validation.py
- check_index_consistency.py
- run_smoke_test.py
- sync_year_docs_to_incoming.py
- preload_llm.py
- enhanced_ocr_processor.py
- validate_codes.py
- reindex_amounts.py
- reclassify_doctype.py
- backfill_model_codes.py
- scan_licenses.py

---

## 다음 작업 (TODO)

1. **미분류 스크립트 분류** (위 14개)
2. **중복 기능 스크립트 통합**
   - OCR 재처리 → force_ocr_update.py로 통합
   - 인제스트 → ingest_from_docs.py로 통합
   - 텍스트 품질 개선 → 통합 검토
3. **deprecated 폴더 생성 및 이동**
   ```bash
   mkdir -p scripts/deprecated
   # 중복 스크립트 이동
   ```
4. **scripts/ 구조 재편**
   ```
   scripts/
   ├── core/           # 운영 필수
   ├── ops/            # 운영 보조
   ├── tools/          # 1회성/실험
   └── deprecated/     # 사용 중지
   ```

---

## 변경 이력

| 날짜 | 변경 내용 | 작성자 |
|------|-----------|--------|
| 2025-11-24 | 초안 작성 (핵심 스크립트 분류) | AI Assistant |
