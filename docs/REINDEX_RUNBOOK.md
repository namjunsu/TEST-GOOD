# 재색인 Runbook (무중단 절차)

**버전:** v2.0
**최종 갱신:** 2025-10-30
**담당:** RAG 인제스트 경로 책임자

---

## 개요

RAG 시스템의 인덱스(BM25, FAISS, DocStore)를 무중단으로 재구축하는 절차를 정의합니다.

**핵심 원칙:**
- **무삭제:** 기존 파일/인덱스는 백업 후 보존
- **원자적 스왑:** 임시 인덱스 생성 후 한 번에 교체
- **검증 필수:** 재색인 전후로 정합성 및 시나리오 검증

---

## 사전 준비

### 1. 환경 검증

```bash
make verify
```

- Tesseract OCR 설치 확인 (`tesseract --version`)
- 한국어 언어팩 확인 (`tesseract --list-langs | grep kor`)
- Python 의존성 확인 (pdfplumber, pytesseract, faiss-cpu 등)

### 2. 복구 태그 생성

```bash
git tag pre-reindex-$(date +%Y%m%d)
git push origin --tags
```

---

## 절차

### STEP 1: 드라이런 (진단 전용)

```bash
python scripts/ingest_dryrun.py \
  --input ./docs \
  --trace reports/ingest_trace.jsonl \
  --chunk-stats reports/chunk_stats.csv \
  --embedding-report reports/embedding_report.json \
  --ocr-audit reports/ocr_audit.md
```

**합격 기준:**
- OCR 실패율 ≤ 5%
- 평균 청크 길이 600~1200 토큰
- 임베딩 오류 0건
- 파일 처리 성공률 ≥ 95%

**실패 시:**
1. `reports/ocr_audit.md`에서 실패 원인 확인
2. Tesseract/언어팩 설치 또는 PDF 수동 검토
3. 수정 후 드라이런 재실행

---

### STEP 2: 재색인 (원자적 스왑)

```bash
python scripts/reindex_atomic.py \
  --source ./docs \
  --tmp-index ./var/index_tmp \
  --swap-to ./var/index \
  --report reports/index_consistency.md
```

**내부 동작:**
1. `./var/index_tmp`에 임시 BM25 인덱스 생성
2. 기존 `./var/index` 백업 (`./var/index_backup_<timestamp>`)
3. 임시 → 타겟으로 원자적 이동
4. 정합성 검증 (`check_index_consistency.py` 자동 호출)

**스왑 로그 예시:**
```
[INFO] 백업 생성: ./var/index_backup_1730280000
[INFO] 스왑: ./var/index_tmp → ./var/index
[INFO] ✅ 스왑 완료
[INDEX] swap done: old=v0, new=v1
```

---

### STEP 3: 정합성 검증

재색인 스크립트가 자동 실행하지만, 수동 재실행도 가능:

```bash
python scripts/check_index_consistency.py \
  --db metadata.db \
  --bm25 rag_system/db/bm25_index.pkl \
  --faiss rag_system/db/faiss.index \
  --report reports/index_consistency.md
```

**합격 기준:**
- DocStore ↔ BM25 키 정합성 100%
- 정합성 점수 ≥ 95%
- 불일치 건수 = 0

**실패 시:**
- `reports/index_consistency.md`에서 누락/중복 키 확인
- 백업에서 롤백: `cp -r ./var/index_backup_<timestamp>/* ./var/index/`
- 원인 파악 후 재색인 재시도

---

### STEP 4: 시나리오 검증 (RAG 품질)

```bash
python scripts/scenario_validation.py --out reports/scenario_after_reindex.json
```

**합격 기준:**
- 성공률 ≥ 95% (8개 시나리오 중 7개 이상 PASS)
- RAG 모드 출처 인용률 100%
- 평균 지연 < 5s (파라미터: DOC_TOPK≤2, LLM_MAX_TOKENS≤512)

**실패 시:**
- `reports/scenario_after_reindex.json`에서 실패 시나리오 확인
- RAG 파라미터 조정 (DOC_TOPK, LLM_MAX_TOKENS, TEMPERATURE)
- 재검증 또는 백업 롤백

---

## Makefile 타겟

### 드라이런

```bash
make ingest-dryrun
```

내부적으로 `python scripts/ingest_dryrun.py --input ./docs ...` 실행

### 재색인

```bash
make reindex
```

내부적으로 `python scripts/reindex_atomic.py --source ./docs ...` 실행

### 정합성 검증

```bash
make check-consistency
```

내부적으로 `python scripts/check_index_consistency.py ...` 실행

### 전체 파이프라인 (드라이런 → 재색인 → 검증)

```bash
make ingest-full
```

---

## 롤백 절차

### 1. 백업에서 복원

```bash
# 최신 백업 확인
ls -lt ./var/index_backup_*

# 복원
cp -r ./var/index_backup_<timestamp>/* ./var/index/
```

### 2. 서비스 재시작

```bash
# 백엔드
sudo systemctl restart ai-chat-backend

# 프론트엔드
sudo systemctl restart ai-chat-ui
```

### 3. 검증

```bash
curl http://localhost:8000/healthz
```

---

## 모니터링 및 알림

### 로그 확인

```bash
# 재색인 로그
tail -f logs/ingest_dryrun_*.log

# 시스템 로그
journalctl -u ai-chat-backend -f
```

### 지표 확인 (UI)

웹 UI → Index Status 패널:
- 문서 수: DB, FAISS, BM25
- 인덱스 버전: `v{timestamp}_{cfg_hash}`
- 최근 재색인 시각
- 정합성 경고 배지

또는 API:

```bash
curl http://localhost:8000/metrics
```

응답 예시:
```json
{
  "docstore_count": 450,
  "faiss_count": 450,
  "bm25_count": 450,
  "unindexed_count": 0,
  "index_version": "v20251030_abc123",
  "last_reindex_at": "2025-10-30T14:30:00Z",
  "ingest_status": "idle"
}
```

---

## FAQ

### Q1. 재색인 중 서비스가 중단되나요?

**A:** 아니요. 원자적 스왑을 사용하므로 무중단입니다. 임시 인덱스를 먼저 생성한 후 한 번에 교체합니다.

### Q2. 재색인 시간은 얼마나 걸리나요?

**A:** 문서 수에 따라 다릅니다:
- 100개: ~5분
- 500개: ~20분
- 1000개: ~40분

### Q3. 재색인 실패 시 자동 롤백되나요?

**A:** 스크립트는 스왑 전에 백업을 자동 생성하지만, 롤백은 수동입니다. 위 롤백 절차를 참고하세요.

### Q4. OCR 실패율이 높으면 어떻게 하나요?

**A:**
1. `reports/ocr_audit.md`에서 실패 사유 확인
2. Tesseract 한국어 언어팩 재설치: `sudo apt-get install tesseract-ocr-kor`
3. 스캔 품질이 낮은 PDF는 수동 OCR 또는 재스캔

### Q5. 정합성 검증 실패 원인은?

**A:**
- DocStore 업데이트 후 BM25/FAISS 미재구축
- 수동 삭제로 인한 키 불일치
- 재색인 중 예외 발생

해결: 재색인 재실행 또는 수동 키 동기화

---

## 체크리스트

재색인 전:
- [ ] 환경 검증 (`make verify`)
- [ ] 복구 태그 생성
- [ ] 디스크 용량 확인 (최소 5GB 여유)

재색인 중:
- [ ] 드라이런 합격 확인
- [ ] 재색인 스크립트 실행
- [ ] 스왑 로그 확인 ("[INDEX] swap done")

재색인 후:
- [ ] 정합성 검증 통과
- [ ] 시나리오 검증 통과
- [ ] UI 지표 확인 (문서 수 일치)
- [ ] `/healthz` 정상 응답

---

## 연락처

문제 발생 시:
- GitHub 이슈: https://github.com/<org>/AI-CHAT/issues
- Slack: #ai-chat-alerts

**End of Runbook**
