# AI-CHAT 주요 기능 및 스크립트 가이드

## 핵심 기능

### 1. 문서 인제스트 (Document Ingestion)
**파일**: `scripts/core/ingest_from_docs.py`

```bash
# 기본 인제스트 (docs/incoming/ 스캔)
.venv/bin/python scripts/core/ingest_from_docs.py

# OCR 자동 폴백 (추천)
.venv/bin/python scripts/core/ingest_from_docs.py --ocr-mode fallback

# OCR 강제 실행
.venv/bin/python scripts/core/ingest_from_docs.py --ocr-mode force

# 특정 파일만 처리
.venv/bin/python scripts/core/ingest_from_docs.py --only "2025-*"

# 최대 10개만 처리
.venv/bin/python scripts/core/ingest_from_docs.py --limit 10

# Dry-run (실제 DB 변경 없이 테스트)
.venv/bin/python scripts/core/ingest_from_docs.py --dry-run
```

**기능**:
- PDF 텍스트 추출 (pdfplumber → Tesseract OCR 폴백)
- 메타데이터 자동 추출 (날짜, 금액, 작성자, 카테고리)
- 중복 파일 감지 (해시 기반)
- SQLite + 텍스트 파일 저장
- 인덱스 자동 업데이트

**출력**:
- `data/extracted/{filename}.txt` - 추출된 텍스트
- `docs/year_{YYYY}/{filename}.pdf` - 연도별 분류
- `metadata.db` - 메타데이터 레코드
- `logs/ingest_{timestamp}.json` - 처리 로그

---

### 2. 검색 인덱스 재빌드

#### BM25 인덱스
**파일**: `scripts/quick_rebuild_bm25.py`

```bash
.venv/bin/python scripts/quick_rebuild_bm25.py
```

**출력**: `var/index/bm25_index.pkl`

**처리 시간**: ~30초 (476개 문서 기준)

#### FAISS 벡터 인덱스
**파일**: `scripts/rebuild_rag_indexes.py`

```bash
.venv/bin/python scripts/rebuild_rag_indexes.py
```

**출력**: `var/index/faiss.index`

**처리 시간**: ~2-3분 (임베딩 생성 포함)

---

### 3. 시스템 헬스체크
**파일**: `scripts/ops/healthcheck.py`

```bash
.venv/bin/python scripts/ops/healthcheck.py
```

**체크 항목**:
- ✅ SQLite DB 연결 상태
- ✅ 파일시스템-DB 동기화
- ✅ 디스크 공간 (90% 경고)
- ✅ 인덱스 파일 존재 여부
- ✅ 메타데이터 품질 (NULL 값 비율)
- ✅ 웹 서버 실행 상태

**출력 예시**:
```
✅ DB 연결: OK (476 documents)
⚠️  동기화: 5개 누락 파일 발견
✅ 디스크: 12.3GB / 50GB (24% 사용)
✅ BM25 인덱스: 최신 (626 docs)
❌ FAISS 인덱스: 미존재
```

---

### 4. OCR 재처리
**파일**: `scripts/ops/ocr_reprocess.py`

```bash
# 텍스트 추출 실패 문서 재처리
.venv/bin/python scripts/ops/ocr_reprocess.py --char-threshold 100

# 특정 문서만
.venv/bin/python scripts/ops/ocr_reprocess.py --doc-id 4982

# Dry-run
.venv/bin/python scripts/ops/ocr_reprocess.py --dry-run
```

**사용 시나리오**:
- 이미지 스캔 PDF가 빈 텍스트로 저장된 경우
- OCR 품질 개선 후 재추출
- Tesseract 업그레이드 후 일괄 재처리

---

### 5. DB 백업 및 복원
**파일**: `scripts/ops/backup_db.py`

```bash
# 백업 생성
.venv/bin/python scripts/ops/backup_db.py

# 백업 저장 위치
# backups/db/metadata.db.YYYYMMDD_HHMMSS.bak
```

**자동 백업 설정** (crontab):
```bash
# 매일 새벽 3시 백업
0 3 * * * cd /home/wnstn4647/AI-CHAT && .venv/bin/python scripts/ops/backup_db.py
```

**복원**:
```bash
# 1. 현재 DB 백업
cp metadata.db metadata.db.emergency_backup

# 2. 백업에서 복원
cp backups/db/metadata.db.20251125_030000.bak metadata.db

# 3. WAL 파일 정리
rm -f metadata.db-shm metadata.db-wal
```

---

### 6. 중복 제거
**파일**: `scripts/ops/cleanup_duplicates.py`

```bash
# Dry-run (추천)
.venv/bin/python scripts/ops/cleanup_duplicates.py --dry-run

# 실제 삭제 실행
.venv/bin/python scripts/ops/cleanup_duplicates.py --execute
```

**감지 방식**:
- SHA256 해시 기반 (동일 파일)
- 정규화 파일명 (공백/특수문자 제거 후 비교)

---

### 7. 파일시스템 동기화 체커
**파일**: `scripts/ops/auto_sync_checker.py`

```bash
# 동기화 상태 확인
.venv/bin/python scripts/ops/auto_sync_checker.py --dry-run

# 자동 복구
.venv/bin/python scripts/ops/auto_sync_checker.py --auto-fix
```

**처리 내용**:
- DB에는 있지만 파일이 없는 경우 → DB 레코드 삭제
- 파일은 있지만 DB에 없는 경우 → 자동 인제스트

---

## 유틸리티 스크립트

### 문서 목록 조회
```bash
# 전체 문서 목록
.venv/bin/python scripts/list_documents.py

# 특정 연도만
.venv/bin/python scripts/list_documents.py --year 2025

# 특정 카테고리만
.venv/bin/python scripts/list_documents.py --category "장비구매"
```

### 메타데이터 검증
```bash
.venv/bin/python scripts/validate_metadata.py
```

**체크 항목**:
- 날짜 형식 오류
- 금액 범위 이상값
- 필수 필드 누락
- 파일 경로 유효성

### 사용 통계 분석
```bash
.venv/bin/python scripts/analyze_usage.py --days 30
```

**출력**:
- 일일 쿼리 수
- 인기 검색어 Top 10
- 평균 응답 시간
- 오류 발생률

---

## RAG 시스템 API

### REST API 엔드포인트

**Base URL**: `http://localhost:7860`

#### 1. 문서 검색
```bash
POST /api/search
Content-Type: application/json

{
  "query": "DVR 구매 내역",
  "top_k": 10,
  "filters": {
    "year": "2024",
    "category": "장비구매"
  }
}
```

#### 2. 질의응답
```bash
POST /api/qa
Content-Type: application/json

{
  "question": "2024년 DVR 구매 비용은 얼마인가요?",
  "use_llm": true,
  "max_context": 5
}
```

#### 3. 문서 메타데이터 조회
```bash
GET /api/documents/{doc_id}
```

#### 4. 헬스체크
```bash
GET /api/health
```

---

## 고급 기능

### 1. 쿼리 라우팅 (Query Routing)

**파일**: `app/rag/query_router.py`

**지원 프로필**:
- `equipment`: 장비/기자재 관련 ("DVR", "카메라", "구매")
- `finance`: 재무/예산 관련 ("예산", "승인", "비용")
- `general`: 일반 문서

**커스터마이징**:
```python
# config/query_routing.yaml
profiles:
  equipment:
    anchors:
      - DVR
      - 카메라
      - 구매
    boost_fields:
      - category
      - title
```

### 2. 동의어 확장 (Synonym Expansion)

**파일**: `config/domain_synonyms.yaml`

```yaml
DVR:
  - 디지털 비디오 레코더
  - 영상 녹화 장치
  - 녹화기

카메라:
  - 캠코더
  - ENG 카메라
  - 촬영 장비
```

**자동 적용**: 검색 시 자동으로 동의어 추가

### 3. 캐싱 시스템

**파일**: `app/rag/persistent_cache.py`

**캐싱 대상**:
- 검색 결과 (쿼리 해시 기반)
- LLM 응답 (컨텍스트 해시 기반)
- 메타데이터 조회

**캐시 무효화**:
```python
from app.rag.persistent_cache import PersistentCache

cache = PersistentCache()
cache.clear_all()  # 전체 삭제
cache.invalidate_query("DVR 구매")  # 특정 쿼리만
```

---

## 트러블슈팅

### 문제 1: "재난방송 문서가 검색 안 됨"

**원인**: DB-파일시스템 불일치

**해결**:
```bash
# 1. 동기화 체크
.venv/bin/python scripts/ops/auto_sync_checker.py --dry-run

# 2. 누락 문서 재인제스트
cp docs/year_2018/2018-01-19_재난방송*.pdf docs/incoming/
.venv/bin/python scripts/core/ingest_from_docs.py

# 3. BM25 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
```

### 문제 2: "OCR 품질 낮음"

**해결**:
```bash
# Tesseract 한국어 데이터 설치
sudo apt-get install tesseract-ocr-kor

# 고품질 모드로 재처리
.venv/bin/python scripts/ops/ocr_reprocess.py --quality high
```

### 문제 3: "검색 속도 느림"

**해결**:
```bash
# 1. 인덱스 최적화
sqlite3 metadata.db "VACUUM;"

# 2. 캐시 워밍
.venv/bin/python scripts/warm_cache.py

# 3. 인덱스 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
.venv/bin/python scripts/rebuild_rag_indexes.py
```

---

## 모범 사례

### 일일 체크리스트
```bash
# 1. 헬스체크 (매일 오전 9시)
.venv/bin/python scripts/ops/healthcheck.py

# 2. 신규 문서 확인 (수시)
ls -l docs/incoming/

# 3. 로그 확인 (오류 발생 시)
tail -f logs/app.log
```

### 주간 유지보수
```bash
# 1. DB 백업 (매주 월요일)
.venv/bin/python scripts/ops/backup_db.py

# 2. 중복 제거 (필요 시)
.venv/bin/python scripts/ops/cleanup_duplicates.py --dry-run

# 3. 성능 리포트
.venv/bin/python scripts/analyze_usage.py --days 7
```

### 월간 작업
```bash
# 1. 전체 인덱스 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
.venv/bin/python scripts/rebuild_rag_indexes.py

# 2. 메타데이터 검증
.venv/bin/python scripts/validate_metadata.py

# 3. 디스크 정리
find logs/ -name "*.log" -mtime +30 -delete
```

---

## 참고 자료

- 시스템 아키텍처: `docs/dev/SYSTEM_ARCHITECTURE_2025.md`
- 운영 가이드: `OPERATIONS_GUIDE.md`
- OCR 가이드: `docs/dev/OCR_UPGRADE_GUIDE.md`
- API 문서: http://localhost:7860/docs
