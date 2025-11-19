# Archive Candidates Review

**날짜**: 2025-11-14
**원본**: `reports/xray/archive_candidates.txt` (23개)

---

## ❌ 제외된 파일 (실제 사용 중)

### app/rag/summary_templates.py
**이유**: 핵심 파이프라인에서 사용 중
**증거**:
- `app/rag/pipeline.py`: `from app.rag.summary_templates import ...`
- `tests/test_consumables_summary.py`: 테스트에서 사용

**위험도**: HIGH - 아카이브 시 파이프라인 중단

---

## ⚠️ 자동 스킵됨 (__init__.py)

스크립트가 자동으로 스킵:
- `app/api/__init__.py`
- `app/config/__init__.py`
- `app/rag/utils/__init__.py`

**이유**: 패키지 구조 보존

---

## 🗑️ 이미 삭제됨 (modules/)

다음 파일들은 `modules/` 폴더 자체가 존재하지 않음:
- `modules/cache_module.py`
- `modules/document_module.py`
- `modules/intent_module.py`
- `modules/llm_module.py`
- `modules/ocr_processor.py`
- `modules/optimized_llm.py`
- `modules/reranker.py`
- `modules/response_formatter.py`
- `modules/statistics_module.py`

**상태**: `modules_legacy/`로 이미 마이그레이션 완료

---

## ✅ 안전하게 아카이브 가능 (10개)

다음 파일들은 프로젝트 루트의 일회성 테스트/유틸리티 스크립트:

1. `check_db_content.py` - DB 점검 도구
2. `diagnose_qa_flow.py` - QA 플로우 진단 도구
3. `everything_like_search.py` - 검색 테스트 도구
4. `fix_metadata_db.py` - DB 수정 도구
5. `health_check.py` - 헬스체크 도구
6. `rebuild_metadata.py` - 메타데이터 재구축 도구
7. `rebuild_rag_indexes.py` - 인덱스 재구축 도구
8. `test_e2e_validation.py` - E2E 검증 스크립트
9. `test_final_validation.py` - 최종 검증 스크립트
10. `verify_golden_queries.py` - 골든 쿼리 검증 스크립트

**저장 위치**: `reports/xray/archive_candidates_safe.txt`

---

## 권장 조치

### 즉시
```bash
# 안전한 리스트로 아카이브 실행
python scripts/apply_archive.py reports/xray/archive_candidates_safe.txt
```

### 향후
- X-Ray 분석 스크립트 개선 (false positive 감소)
- `app/rag/summary_templates.py` 사용 추적 로직 추가
