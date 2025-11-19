# 운영 체크리스트 (Operations Checklist)

**Version**: v1.0.0
**Last Updated**: 2025-11-14
**Purpose**: AI-CHAT RAG 시스템 정기 점검 및 대규모 코드 정리 전 실행 가이드

---

## 1. 정기 점검 루틴 (분기/반기 1회)

### 1.1 코드베이스 상태 스냅샷
```bash
# 레포 전체 상태: Python 파일 수, 라인 수, dead code, 의존성
bash scripts/audit_repo.sh

# 결과 확인
cat reports/src_stats.json
cat reports/vulture.txt
cat reports/deps/pipdeptree.txt
cat reports/deps/requirements_frozen.txt
```

**확인 항목**:
- Python 파일 수가 급증하지 않았는지 (현재 기준: 198개)
- Total lines 증가 추세 (현재 기준: 53,267줄)
- `vulture.txt`에서 dead code 0개 유지되는지
- 의존성에서 보안 취약점 경고 없는지

---

### 1.2 미사용 코드 휴리스틱 분석
```bash
# 사용/미사용 파일 휴리스틱 분석 (ripgrep 필요)
python scripts/audit_usage.py

# 결과 확인
cat reports/USAGE_AUDIT.md
cat reports/usage_audit_raw.json
```

**확인 항목**:
- Unused 파일 수 추이 (현재 기준: 66개 의심)
- 새로 추가된 UNUSED 파일이 있는지
- 기존 UNUSED → USED로 바뀐 파일 (재사용된 코드)

**주의**: 이 스크립트는 휴리스틱 기반이므로 **삭제 기준이 아님**. 실제 정리 전에 수동 검토 필수.

---

### 1.3 문서 결손 점검 (RAG 품질 점검)
```bash
# 인덱스/DB 상태: content 필드 누락/짧은 문서 탐지
python scripts/audit_missing_content.py --min-len 50

# 임계값 조정 시
RAG_MIN_CONTENT_LEN=100 python scripts/audit_missing_content.py
```

**확인 항목**:
- 결손 문서 비율 (목표: < 5%)
- 결손 문서가 증가 추세인지 (OCR 품질 저하 가능성)
- `var/index/bm25_index.pkl`, `var/index/korean_vector_index.faiss` 파일 크기 추이

**조치**:
- 결손 문서 > 10% 시: `python scripts/rebuild_indexes_v2.py` 재실행
- 특정 PDF가 반복적으로 결손 시: OCR 파라미터 조정 또는 수동 추출

---

## 2. 대규모 코드 정리 전 실행 스크립트

**목적**: 안전한 코드 정리를 위해 삭제/아카이브 후보를 검증하고 백업 생성

### 2.1 실행 순서

#### STEP 1: 현재 상태 스냅샷 생성
```bash
# 1. 레포 상태 기록
bash scripts/audit_repo.sh

# 2. 사용성 분석
python scripts/audit_usage.py

# 3. git 커밋 전 상태 저장
git status > reports/git_status_before_cleanup.txt
git diff > reports/git_diff_before_cleanup.txt
```

#### STEP 2: 후보 파일 수동 검토
```bash
# USAGE_AUDIT.md에서 UNUSED 66개 확인
cat reports/USAGE_AUDIT.md

# X-Ray 분석 (이전 작업 결과 참고)
cat reports/xray/archive_candidates_REVIEW.md
cat reports/xray/archive_candidates_safe.txt
```

**검토 기준**:
- `__init__.py`: 절대 삭제 금지 (패키지 구조)
- `conftest.py`, `setup.py`: pytest/설치 관련, 보존
- `tests/test_*.py`: 미사용이어도 레거시 테스트로 보존 (modules_legacy/ 이동 고려)
- `app/rag/summary_templates.py` 같은 오탐 제거 (실제 import 확인)

#### STEP 3: 안전한 후보 리스트 생성
```bash
# 예: 수동 검토 후 안전한 10개만 선별
cat > reports/xray/archive_candidates_safe_v2.txt <<EOF
scripts/old_tool_1.py
scripts/old_tool_2.py
utils/deprecated_helper.py
...
EOF
```

#### STEP 4: 아카이브 실행 (삭제 X)
```bash
# DRY-RUN 먼저
python scripts/apply_archive.py reports/xray/archive_candidates_safe_v2.txt

# 실제 실행 (archive/YYYY-MM-DD/로 이동)
# 스크립트 내부에서 interactive 확인 포함됨
```

#### STEP 5: import 테스트 + 서비스 재기동
```bash
# 핵심 모듈 import 테스트
.venv/bin/python -c "
import app.api.main
import app.data.metadata_db
import app.rag.retriever
import app.textproc.normalizer
print('✅ All imports OK')
"

# 서비스 재기동
pkill -f "uvicorn|streamlit" || true
nohup .venv/bin/python -m uvicorn app.api.main:app --host 0.0.0.0 --port 7860 >/tmp/api.log 2>&1 &
nohup .venv/bin/python -m streamlit run web_interface.py --server.port 8501 --server.headless true >/tmp/ui.log 2>&1 &

# 헬스체크
sleep 5
curl http://127.0.0.1:7860/_healthz
curl http://127.0.0.1:8501/_stcore/health
```

#### STEP 6: 스모크 테스트
```bash
# 2건 질의 + 1건 금액 추출
timeout 90 python3 scripts/validate_askable_queries.py

# 또는 web UI에서 수동 테스트
# - "VARICAM HS 관련 문서 찾아줘"
# - "2022-08-22 LED 조명 수리 금액?"
```

---

## 3. 인덱스 백필/재구축 작업

### 3.1 model_codes 백필 (기존 문서용)
```bash
# 전체 문서에서 model_codes 추출
python scripts/backfill_model_codes.py

# 일부만 테스트 (처음 50개)
python scripts/backfill_model_codes.py --limit 50

# DRY-RUN 모드
python scripts/backfill_model_codes.py --dry-run
```

**실행 시점**:
- `model_codes` 테이블 스키마 변경 후
- 대량 문서 추가 후 (50+ 신규 PDF)

---

### 3.2 BM25 + Vector Index 재구축
```bash
# 전체 재인덱싱 (473 문서 기준 ~5분 소요)
python scripts/rebuild_indexes_v2.py

# 빠른 재구축 (BM25만)
python scripts/quick_rebuild_bm25.py
```

**실행 시점**:
- OCR 파라미터 변경 후
- 100+ 신규 문서 추가 후
- 검색 품질 저하 감지 시 (exact_match_hit_rate < 0.70)

---

## 4. 결과 리포트 확인 항목

### 4.1 audit_repo.sh 결과
```json
// reports/src_stats.json
{
  "py_files": 198,      // 급증 시 코드 리뷰 필요
  "lines": 53267,       // 10% 이상 증가 시 아키텍처 점검
  "folders": [...],     // 새 폴더 생성 시 구조 변경 의심
  "modules": [...]      // 새 top-level 모듈 추가 여부
}
```

### 4.2 audit_usage.py 결과
```markdown
// reports/USAGE_AUDIT.md
## Unused Files (suspected)
| File | Status | Reason |
|------|--------|--------|
| app/alerts.py | UNUSED | No imports, not CLI, not special |
...
```

**조치 우선순위**:
1. `scripts/`, `utils/`: 안전하게 archive/ 이동 가능
2. `tests/`: modules_legacy/ 또는 보존
3. `app/`, `components/`: 실제 import 재확인 필수 (오탐 가능성)

### 4.3 audit_missing_content.py 결과
```
결손 문서 수: 12개 (2.5%)
목록:
  - 2020-12-29_조명용_멀티탭_구매_건.pdf (content_len=8)
  - 2022-05-30_영상취재팀_헬리캠_수리_건.pdf (content_len=15)
```

**조치**:
- < 5%: 정상 (일부 스캔 품질 문제는 불가피)
- 5-10%: 주의 (OCR 파라미터 검토)
- > 10%: 위험 (전체 재인덱싱 또는 PDF 원본 점검)

---

## 5. 운영 메트릭 모니터링

### 5.1 RAG 품질 지표 (/metrics 엔드포인트)
```bash
curl http://127.0.0.1:7860/metrics | jq
```

**목표치** (RELEASE_NOTES 기준):
- `low_conf_triggered / total_queries` ≤ 0.25
- `retrieval_latency_ms_p95` < 3000
- `exact_match_hit_rate` ≥ 0.80

### 5.2 문서 규모별 최적화 임계값
| 문서 수 | 조치 |
|--------|------|
| 500+ | BM25 k1/b 파라미터 튜닝 |
| 1000+ | FAISS index_factory → IVF128,PQ32 |
| 2000+ | reranker top_k 조정 (30 → 50) |

---

## 6. 체크리스트 요약

### 분기 점검 (3개월마다)
- [ ] `bash scripts/audit_repo.sh` 실행
- [ ] `python scripts/audit_usage.py` 실행
- [ ] `python scripts/audit_missing_content.py` 실행
- [ ] dead code = 0 확인
- [ ] 결손 문서 < 5% 확인
- [ ] 의존성 보안 취약점 확인 (pipdeptree, pip-audit)

### 대규모 정리 전
- [ ] git status/diff 백업
- [ ] 후보 파일 수동 검토 (오탐 제거)
- [ ] archive_candidates_safe.txt 생성
- [ ] apply_archive.py 실행
- [ ] import 테스트
- [ ] 서비스 재기동 + 헬스체크
- [ ] 스모크 테스트 (2건 질의)

### 긴급 대응
- [ ] 검색 품질 저하 시: rebuild_indexes_v2.py
- [ ] 신규 문서 100+ 추가 시: rebuild_indexes_v2.py
- [ ] model_codes 누락 시: backfill_model_codes.py
- [ ] 서비스 장애 시: /tmp/api.log, /tmp/ui.log 확인

---

## 7. 참고 문서

- **릴리즈 노트**: `docs/dev/RELEASE_NOTES_v2025-11-14.md`
- **X-Ray 분석**: `reports/xray/archive_candidates_REVIEW.md`
- **테스트 결과**: 24 PASS + 9 XFAIL (All Green)
- **현재 인덱스**: 473 문서, BM25 + Korean Vector

---

**이 체크리스트는 v1.0.0 기준으로 작성되었으며, 시스템 변경에 따라 업데이트 필요합니다.**
