# ExactMatchRetriever v2.0 운영 모니터링 가이드

**버전**: v2.0
**작성일**: 2025-11-11
**대상**: 운영팀, SRE

---

## 1. 개요

ExactMatchRetriever v2.0은 RAG 시스템의 Stage 0 (정확일치 단계)로, 모델번호/부품코드 질의에 대해 **오검출 최소화를 최우선**으로 하는 정밀 검색기입니다.

### 핵심 설계 원칙
- **오검출 최소화 > 재현율**: False Positive 방지가 최우선
- **빠른 실패**: 코드 패턴 미발견 시 즉시 Stage 1 (BM25)로 위임
- **경계 제약**: `HRD-442` ≠ `HRD-4420` (padded_norm 기반 단어 경계 검증)

### 주요 개선 사항 (v1 → v2)
1. SQLite 인덱스 최적화 (COLLATE NOCASE, 배치 쿼리)
2. LIKE 경계 제약 (padded_norm 컬럼)
3. 특수문자 이스케이프
4. 스코어 정규화 (0-10 범위)
5. 메트릭 수집 (hit_rate, query_time)

---

## 2. 메트릭 사양

### 2.1 실시간 메트릭 (Runtime Metrics)

#### `/metrics` 엔드포인트 응답 예시
```json
{
  "retriever_runtime": {
    "retriever_config": {
      "enabled": true,
      "version": "2.0"
    },
    "exact_match": {
      "total_queries": 1523,
      "exact_hits": 647,
      "filename_hits": 89,
      "total_query_time_ms": 34256.8,
      "exact_match_hit_rate": 0.4247,
      "avg_query_time_ms": 22.49
    }
  }
}
```

#### 메트릭 정의

| 메트릭명 | 타입 | 설명 | 정상 범위 |
|---------|------|------|----------|
| `total_queries` | int | 누적 질의 수 (프로세스 시작 이후) | 증가 추세 |
| `exact_hits` | int | 코드 정확일치 건수 (norm_code IN 쿼리) | - |
| `filename_hits` | int | 파일명 부분일치 건수 (COLLATE NOCASE) | - |
| `total_query_time_ms` | float | 누적 검색 시간 (ms) | - |
| `exact_match_hit_rate` | float | 정확일치 적중률 (exact_hits / total_queries) | **0.35 ~ 0.65** |
| `avg_query_time_ms` | float | 평균 검색 시간 (ms) | **< 80 (p95)** |

### 2.2 파생 메트릭 (Derived Metrics)

다음 메트릭은 모니터링 시스템에서 계산해야 합니다:

```python
# Prometheus PromQL 예시
# p95 레이턴시 (5분 윈도우)
histogram_quantile(0.95,
  rate(exact_match_query_duration_seconds_bucket[5m])
)

# 5분 평균 hit_rate
rate(exact_match_hits_total[5m]) / rate(exact_match_queries_total[5m])
```

---

## 3. 알람 임계치

### 3.1 WARNING 레벨

| 조건 | 임계치 | 측정 주기 | 조치 사항 |
|-----|--------|----------|---------|
| **낮은 적중률** | `exact_match_hit_rate < 0.35` | 5분 평균 | 1. 코드 패턴 확인<br>2. 정규화 로직 점검<br>3. 신규 모델번호 DB 반영 여부 확인 |
| **높은 레이턴시** | `avg_query_time_ms > 80` (p95) | 5분 평균 | 1. DB 인덱스 상태 확인 (`EXPLAIN QUERY PLAN`)<br>2. 커넥션 풀 사용률 확인<br>3. 디스크 I/O 부하 확인 |
| **과도한 파일명 의존** | `filename_hits / total_queries > 0.25` | 10분 평균 | 1. 코드 추출 정확도 저하 의심<br>2. 최근 ingestion 로그 확인 |

### 3.2 CRITICAL 레벨

| 조건 | 임계치 | 측정 주기 | 조치 사항 |
|-----|--------|----------|---------|
| **극심한 레이턴시** | `avg_query_time_ms > 150` (p95) | 5분 평균 | 1. **즉시 Feature Flag OFF 검토** (`ENABLE_EXACT_MATCH=false`)<br>2. Stage 1 (BM25)로 폴백 확인<br>3. DB 락 확인 (`PRAGMA lock_status`) |
| **API 장애** | `5xx_rate > 0.5%` 또는 `timeout_rate > 1%` | 3분 평균 | 1. **롤백 준비** (v1 복구 스크립트 실행)<br>2. DB 마이그레이션 무결성 검증<br>3. 에러 로그 스택트레이스 분석 |
| **DB 손상 의심** | `padded_norm IS NULL` 비율 > 5% | 실시간 | 1. **서비스 중단 검토**<br>2. DB 백업에서 복구<br>3. 마이그레이션 재실행 |

---

## 4. 데이터베이스 스키마

### 4.1 model_codes 테이블

```sql
CREATE TABLE model_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    code TEXT NOT NULL,           -- 원본 코드 (예: "XRN-1620B2")
    norm_code TEXT NOT NULL,      -- 정규화 코드 (예: "XRN1620B2")
    padded_norm TEXT,             -- 경계 제약용 (예: " XRN1620B2 ")
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);

-- 필수 인덱스
CREATE INDEX idx_model_codes_norm ON model_codes(norm_code);
CREATE INDEX idx_model_codes_padded ON model_codes(padded_norm);
CREATE INDEX idx_model_codes_doc ON model_codes(doc_id);
```

### 4.2 documents 테이블 (인덱스만)

```sql
-- COLLATE NOCASE로 대소문자 무시 검색 지원
CREATE INDEX idx_documents_filename_nocase ON documents(filename COLLATE NOCASE);
```

### 4.3 인덱스 검증

인덱스 사용 여부 확인:
```bash
python scripts/verify_exact_match_indexes.py
```

출력 예시:
```
📋 테이블: model_codes
----------------------------------------------------------------------
  idx_model_codes_norm: ✅ 존재
  idx_model_codes_padded: ✅ 존재

🔍 EXPLAIN QUERY PLAN 검증
----------------------------------------------------------------------
1️⃣ model_codes IN 쿼리 (정확일치)
  Query: SELECT DISTINCT doc_id FROM model_codes WHERE norm_code IN (?, ?, ?)
  Plan:
    → SEARCH model_codes USING INDEX idx_model_codes_norm (norm_code=?)
      ✅ 인덱스 활용
```

**⚠️ "SCAN TABLE" 출력 시 인덱스 미사용 → 즉시 재생성 필요**

---

## 5. Feature Flag 제어

### 5.1 환경 변수

```bash
# .env 파일
ENABLE_EXACT_MATCH=true   # v2.0 활성화 (기본값: true)
```

### 5.2 런타임 토글 (재시작 필요)

```bash
# v2.0 비활성화 (Stage 1 BM25로 즉시 폴백)
export ENABLE_EXACT_MATCH=false
pkill -f "uvicorn"
nohup uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &

# v2.0 재활성화
export ENABLE_EXACT_MATCH=true
pkill -f "uvicorn"
nohup uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
```

### 5.3 검증

```bash
# /metrics 엔드포인트 확인
curl -s http://localhost:7860/metrics | jq '.retriever_runtime.retriever_config'

# 출력:
# {
#   "enabled": true,
#   "version": "2.0"
# }
```

---

## 6. 롤백 절차

### 6.1 긴급 롤백 (< 5분)

**상황**: CRITICAL 알람 발생 + 서비스 장애

1. **Feature Flag OFF**
   ```bash
   export ENABLE_EXACT_MATCH=false
   pkill -f "uvicorn"
   nohup uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
   ```

2. **검증**
   ```bash
   curl -s http://localhost:7860/metrics | jq '.retriever_runtime.exact_match'
   # 출력: null (비활성화 확인)
   ```

3. **모니터링**
   - 5xx 에러율 정상화 확인 (< 0.1%)
   - p95 레이턴시 확인 (< 2000ms, Stage 1 기준)

### 6.2 DB 롤백 (< 10분)

**상황**: DB 손상 의심 (padded_norm NULL 비율 > 5%)

1. **백업 복구**
   ```bash
   cp var/metadata.db var/metadata.db.broken
   cp var/backups/metadata.db.backup-YYYYMMDD var/metadata.db
   ```

2. **인덱스 재생성**
   ```bash
   python scripts/migrate_exact_match_indexes.py
   ```

3. **검증**
   ```bash
   python scripts/verify_exact_match_indexes.py
   pytest tests/test_exact_match_contract.py -v
   ```

### 6.3 코드 롤백 (< 15분)

**상황**: 버그 발견 + 핫픽스 불가

```bash
# Git 롤백
git revert HEAD --no-edit
git push origin main

# 재배포
pkill -f "uvicorn"
nohup uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
```

---

## 7. 배포 절차 (Canary)

### 7.1 단계별 배포

| 단계 | 트래픽 비율 | 소요 시간 | 검증 항목 |
|-----|-----------|----------|---------|
| **1. Canary** | 10% | 2시간 | - 5xx < 0.1%<br>- p95 < 100ms<br>- hit_rate 0.35~0.65 |
| **2. Ramp-up** | 50% | 2시간 | - 상동<br>- DB 커넥션 풀 여유 (> 30%) |
| **3. Full** | 100% | - | - 24시간 모니터링 시작 |

### 7.2 검증 체크리스트

각 단계 후 실행:

```bash
# 1. 계약 테스트
pytest tests/test_exact_match_contract.py -v

# 2. 골든 파일 테스트 (추후 작성)
pytest tests/test_exact_match_golden.py -v

# 3. 메트릭 확인
curl -s http://localhost:7860/metrics | jq '.retriever_runtime'

# 4. 로그 에러 확인 (최근 10분)
tail -100 /tmp/api.log | grep -i "error\|exception"
```

---

## 8. 트러블슈팅

### 8.1 낮은 적중률 (hit_rate < 0.35)

**원인 분석**:
1. 최근 ingestion에서 코드 추출 실패?
   ```bash
   # 최근 문서의 model_codes 개수 확인
   sqlite3 var/metadata.db "SELECT doc_id, COUNT(*) FROM model_codes GROUP BY doc_id ORDER BY id DESC LIMIT 10;"
   ```

2. 정규화 로직 변경으로 기존 DB와 불일치?
   ```bash
   # 샘플 쿼리로 직접 확인
   sqlite3 var/metadata.db "SELECT norm_code, padded_norm FROM model_codes WHERE code LIKE '%XRN%' LIMIT 5;"
   ```

**해결 방안**:
- 코드 추출 정확도 저하 → `app/extractors/device_fields.py` 점검
- 정규화 불일치 → 전체 재ingestion 검토

### 8.2 높은 레이턴시 (p95 > 80ms)

**원인 분석**:
1. 인덱스 미사용?
   ```bash
   python scripts/verify_exact_match_indexes.py | grep "SCAN TABLE"
   ```

2. DB 파일 크기 비대?
   ```bash
   du -h var/metadata.db
   sqlite3 var/metadata.db "VACUUM;"  # 공간 회수
   ```

**해결 방안**:
- SCAN TABLE 발견 → 인덱스 재생성
- DB 비대 → VACUUM 실행

### 8.3 DB 손상 (padded_norm NULL)

**긴급 복구**:
```bash
# 1. 백업 확인
ls -lh var/backups/*.db

# 2. 복구
cp var/backups/metadata.db.backup-YYYYMMDD var/metadata.db

# 3. 마이그레이션 재실행
python scripts/migrate_exact_match_indexes.py

# 4. 검증
sqlite3 var/metadata.db "SELECT COUNT(*) FROM model_codes WHERE norm_code IS NOT NULL AND padded_norm IS NULL;"
# 출력: 0 (정상)
```

---

## 9. 로그 분석

### 9.1 중요 로그 패턴

```python
# Stage 0 적중 (정상)
logger.info(f"🎯 Stage 0 (ExactMatch): {len(exact_results)}건 반환, 하위 Stage 스킵")

# Stage 0 미적중 → Stage 1 폴백 (정상)
logger.debug("Stage 0: 코드 패턴 미발견, Stage 1로 진행")

# DB 쿼리 에러 (비정상)
logger.error(f"model_codes 쿼리 실패: {e}", exc_info=True)

# 스코어 클리핑 경고 (비정상, 드물어야 함)
logger.warning(f"스코어 범위 초과 클리핑: {raw_score} → 10.0")
```

### 9.2 로그 필터링

```bash
# Stage 0 적중 건수 (최근 1시간)
grep "Stage 0 (ExactMatch)" /tmp/api.log | tail -1000 | wc -l

# 에러 발생 건수
grep -i "error\|exception" /tmp/api.log | tail -100
```

---

## 10. 성능 벤치마크

### 10.1 목표 성능 (v2.0)

| 지표 | 목표 | 측정 방법 |
|-----|------|---------|
| **p50 레이턴시** | < 30ms | `avg_query_time_ms` (정상 트래픽) |
| **p95 레이턴시** | < 80ms | 모니터링 시스템 histogram_quantile |
| **p99 레이턴시** | < 150ms | 상동 |
| **적중률** | 0.35 ~ 0.65 | `exact_match_hit_rate` (5분 평균) |
| **에러율** | < 0.1% | FastAPI 5xx / total_requests |

### 10.2 부하 테스트 (추후 실행)

```bash
# Apache Bench (20 RPS, 1분)
ab -n 1200 -c 4 -p test_query.json -T application/json http://localhost:7860/ask

# 예상 결과:
# - 성공률 > 99.9%
# - p95 < 80ms
# - DB 커넥션 풀 여유 > 30%
```

---

## 11. 관련 문서

- **계약 테스트**: `tests/test_exact_match_contract.py`
- **마이그레이션 스크립트**: `scripts/migrate_exact_match_indexes.py`
- **인덱스 검증 스크립트**: `scripts/verify_exact_match_indexes.py`
- **소스 코드**: `app/rag/retrievers/exact_match.py`
- **통합 검색**: `app/rag/retrievers/hybrid.py`

---

## 12. 담당자 연락처

| 역할 | 담당자 | 연락처 |
|-----|--------|--------|
| **개발** | AI Team | - |
| **운영** | SRE Team | - |
| **On-call** | Rotation | - |

---

**최종 수정**: 2025-11-11
**문서 버전**: 1.0
