# AI-CHAT 운영 가이드

**최종 업데이트**: 2025-12-11
**시스템**: RAG 기반 문서 Q&A 시스템
**환경**: WSL2, Python 3.12, RTX 4060

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [빠른 시작](#2-빠른-시작)
3. [문서 관리](#3-문서-관리)
4. [환경 설정](#4-환경-설정)
5. [서비스 운영](#5-서비스-운영)
6. [모니터링](#6-모니터링)
7. [백업 및 복구](#7-백업-및-복구)
8. [트러블슈팅](#8-트러블슈팅)
9. [보안 설정](#9-보안-설정)
10. [SLO 및 품질 가드](#10-slo-및-품질-가드)
11. [캐시 시스템](#11-캐시-시스템)
12. [ExactMatch 모니터링](#12-exactmatch-모니터링)

---

## 1. 시스템 개요

### 1.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG 시스템 데이터 흐름                                │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   원본 PDF    │  ← 진실의 원천 (Source of Truth)
    │  docs/year_* │     469개 PDF 파일
    └──────┬───────┘
           │
           │ (1) 텍스트 추출 (pdfplumber + OCR)
           ▼
    ┌──────────────┐
    │ 추출된 텍스트  │  ← 검색용 텍스트
    │data/extracted│     469개 .txt 파일
    └──────┬───────┘
           │
           │ (2) 메타데이터 파싱
           ▼
    ┌──────────────┐
    │ 메타데이터 DB  │  ← 필터링/목록 표시용
    │  metadata.db │     날짜, 작성자, 카테고리 등
    └──────┬───────┘
           │
           │ (3) 인덱싱
           ▼
    ┌──────────────┐
    │  BM25 인덱스  │  ← 키워드 검색용
    │  var/index/  │     토큰화된 검색 인덱스
    └──────────────┘
```

### 1.2 디렉토리 구조

```
AI-CHAT/
├── docs/                      # 원본 PDF 문서
│   ├── year_2020~2025/       # 연도별 폴더
│   ├── incoming/             # 신규 문서 대기 폴더
│   └── quarantine/           # 삭제된 문서 백업
│
├── data/
│   └── extracted/            # 텍스트 추출 파일 (.txt)
│
├── metadata.db               # 메타데이터 DB (SQLite)
│
├── var/
│   └── index/                # BM25 검색 인덱스
│       └── bm25_index.pkl
│
├── scripts/
│   ├── ops/                  # 운영 스크립트
│   │   ├── add_docs.sh       # 문서 추가
│   │   ├── delete_doc.sh     # 문서 삭제
│   │   ├── list_docs.sh      # 문서 목록
│   │   ├── set_meta.sh       # 메타데이터 수정
│   │   └── healthcheck.py    # 헬스체크
│   └── core/                 # 핵심 스크립트
│       ├── ingest_from_docs.py
│       └── reindex_atomic.py
│
└── app/                      # 애플리케이션 코드
    ├── api/                  # FastAPI 백엔드
    └── rag/                  # RAG 파이프라인
```

### 1.3 핵심 컴포넌트

| 컴포넌트 | 역할 | 위치 |
|----------|------|------|
| **원본 PDF** | 진실의 원천, 보존 목적 | `docs/year_*/*.pdf` |
| **추출 텍스트** | AI가 읽고 검색하는 텍스트 | `data/extracted/*.txt` |
| **메타데이터 DB** | 날짜, 작성자 등 필터링용 | `metadata.db` |
| **BM25 인덱스** | 키워드 검색용 인덱스 | `var/index/bm25_index.pkl` |
| **FastAPI** | REST API (port 7860) | `app/api/main.py` |
| **Streamlit** | 웹 UI (port 8501) | `web_interface.py` |

---

## 2. 빠른 시작

### 2.1 서비스 시작

```bash
# 백엔드 + 자동 인덱서 시작
bash start_ai_chat.sh

# 별도 터미널에서 UI 시작
streamlit run web_interface.py --server.port 8501 --server.headless true
```

### 2.2 서비스 종료

```bash
pkill -f "uvicorn app.api.main"
pkill -f "streamlit run web_interface"
pkill -f "auto_indexer.py"
```

### 2.3 상태 확인

```bash
# 문서 통계
./scripts/ops/list_docs.sh --stats

# 헬스체크
./scripts/ops/healthcheck.py

# API 헬스
curl -s http://localhost:7860/_healthz
```

---

## 3. 문서 관리

### 3.1 문서 추가

```bash
# 단일 파일 추가
./scripts/ops/add_docs.sh /path/to/document.pdf

# 여러 파일 추가
./scripts/ops/add_docs.sh /path/to/*.pdf

# incoming 폴더의 모든 파일 처리
cp /path/to/*.pdf docs/incoming/
./scripts/ops/add_docs.sh
```

**파일명 규칙 (권장)**:
```
YYYY-MM-DD_제목_부가정보.pdf

예시:
2024-01-15_UPS장비구매_기안서.pdf
2024-03-20_서버실_공조기_점검보고서.pdf
```

### 3.2 문서 삭제

```bash
# 파일명으로 삭제 (백업 유지)
./scripts/ops/delete_doc.sh "2024-01-15_장비구매.pdf"

# ID로 삭제
./scripts/ops/delete_doc.sh --id 123

# 검색 후 삭제
./scripts/ops/delete_doc.sh --search "UPS 구매"

# 완전 삭제 (복구 불가)
./scripts/ops/delete_doc.sh --id 123 --no-backup --force
```

**삭제된 문서 복구**:
```bash
mv docs/quarantine/document.pdf docs/incoming/
./scripts/ops/add_docs.sh
```

### 3.3 문서 목록 조회

```bash
# 최근 문서 50개
./scripts/ops/list_docs.sh

# 전체 목록
./scripts/ops/list_docs.sh --all

# 연도별 필터
./scripts/ops/list_docs.sh --year 2024

# 작성자별 필터
./scripts/ops/list_docs.sh --drafter 하승범

# 키워드 검색
./scripts/ops/list_docs.sh --search "UPS"

# 통계 보기
./scripts/ops/list_docs.sh --stats

# 메타데이터 누락 문서
./scripts/ops/list_docs.sh --missing
```

### 3.4 메타데이터 수정

```bash
# 날짜 수정
./scripts/ops/set_meta.sh --id 123 --date 2024-01-15

# 작성자 수정
./scripts/ops/set_meta.sh --id 123 --drafter 하승범

# 카테고리 수정
./scripts/ops/set_meta.sh --id 123 --category review

# 여러 항목 동시 수정
./scripts/ops/set_meta.sh --id 123 --date 2024-01-15 --drafter 하승범 --category report

# 텍스트에서 메타데이터 재추출
./scripts/ops/set_meta.sh --reparse 123

# 전체 문서 재추출
./scripts/ops/set_meta.sh --reparse-all
```

**카테고리 종류**:

| 코드 | 설명 |
|------|------|
| proposal | 기안서 |
| review | 검토서 |
| report | 보고서 |
| minutes | 회의록 |
| disposal | 폐기/불용 |
| other | 기타 |

### 3.5 인덱스 재생성

```bash
# 자동 인덱서가 10초마다 변경 감지
# 수동 재생성이 필요한 경우:
.venv/bin/python3 scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index
```

---

## 4. 환경 설정

### 4.1 필수 환경변수 (.env)

```bash
# ============================================================================
# 운용 모드 설정
# ============================================================================
MODE=AUTO                    # AUTO | SUMMARIZE | CHAT
RAG_MIN_SCORE=0.35          # RAG 모드 진입 임계값 (0.25~0.50)
DOC_TOPK=3                  # 상위 문서 개수
REQUIRE_CITATIONS=true      # 출처 인용 강제
ALLOW_UNGROUNDED_CHAT=true  # 근거 없을 때 일반 대화 허용

# ============================================================================
# 모델 설정
# ============================================================================
MODEL_PATH=./models/your-model.gguf
CHAT_FORMAT=auto            # auto | llama-2 | qwen | chatml
N_CTX=4096                  # 컨텍스트 크기
N_GPU_LAYERS=-1             # -1: 전체 GPU, 양수: 부분 GPU

# ============================================================================
# LLM 생성 파라미터
# ============================================================================
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=2048
MAX_LLM_RETRY=1

# ============================================================================
# 검색 설정
# ============================================================================
SEARCH_BM25_WEIGHT=0.99     # BM25 가중치 (OCR 텍스트는 키워드 기반이 정확)
SEARCH_VECTOR_WEIGHT=0.01   # 벡터 검색 가중치
SEARCH_TOP_K=5              # 검색 결과 개수

# ============================================================================
# 디렉토리 설정
# ============================================================================
DOCS_DIR=docs
DATA_DIR=data
INCOMING_DIR=incoming
LOG_DIR=logs
LOG_LEVEL=INFO

# ============================================================================
# 서버 포트
# ============================================================================
API_PORT=7860
UI_PORT=8501
```

### 4.2 RAG_MIN_SCORE 가이드

| 값 | 효과 |
|----|------|
| 0.25 | 매우 관대 (약한 연관성도 RAG) |
| **0.35 (권장)** | 균형 (중간 연관성 이상 RAG) |
| 0.50 | 엄격 (강한 연관성만 RAG) |

---

## 5. 서비스 운영

### 5.1 시작/종료

**시작 (스크립트 사용)**:
```bash
bash start_ai_chat.sh
# "Drop and rebuild index? (y/n)" → 평상시 'n'

# UI는 별도 터미널에서
streamlit run web_interface.py --server.port 8501
```

**수동 시작**:
```bash
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &
nohup python scripts/utils/auto_indexer.py > logs/auto_indexer.log 2>&1 &
streamlit run web_interface.py --server.port 8501
```

**종료**:
```bash
pkill -f "uvicorn app.api.main"
pkill -f "streamlit run web_interface"
pkill -f "auto_indexer.py"
```

### 5.2 헬스체크

```bash
# API 헬스
curl -s http://localhost:7860/_healthz
# Expected: {"status": "ok"}

# DB 무결성
sqlite3 metadata.db "PRAGMA integrity_check;"
# Expected: "ok"

# 프로세스 확인
pgrep -a -f "uvicorn|streamlit|auto_indexer"

# 포트 확인
ss -tulpn | grep -E '7860|8501'
```

### 5.3 로그 관리

**로그 위치**:

| 파일 | 용도 | 로테이션 |
|------|------|----------|
| `logs/ai-chat.log` | 전체 로그 (INFO+) | 일별, 7일 보존 |
| `logs/ai-chat-error.log` | 에러만 (ERROR+) | 일별, 7일 보존 |
| `logs/auto_indexer.log` | 백그라운드 인덱싱 | 수동 |

**로그 확인**:
```bash
# 실시간 로그
tail -f logs/ai-chat.log

# 에러만 보기
grep "ERROR" logs/ai-chat.log

# 최근 에러 100줄
tail -100 logs/ai-chat-error.log
```

---

## 6. 모니터링

### 6.1 /metrics 엔드포인트

```bash
curl -s http://localhost:7860/metrics | jq '.'
```

**주요 지표**:

| 지표 | 설명 | 목표 | 경보 임계값 |
|------|------|------|------------|
| `stale_index_entries` | 인덱스-파일 불일치 | 0 | > 0 |
| `fs_file_count` | 파일 시스템 문서 수 | - | - |
| `index_file_count` | 인덱스 문서 수 | ≈ fs_file_count | 차이 > 5 |
| `json_parse_failure_rate` | JSON 파싱 실패율 | < 1.5% | > 2% |
| `coverage_p50` | 검색 커버리지 중앙값 | > 0.80 | < 0.80 |

### 6.2 GPU 모니터링

```bash
# 실시간 모니터링
watch -n 1 nvidia-smi

# GPU 사용량 기록
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits
```

---

## 7. 백업 및 복구

### 7.1 백업 대상

1. `metadata.db` - 문서 메타데이터 (필수)
2. `var/index/` - BM25 인덱스 (재생성 가능)
3. `.env` - 설정 (필수, 보안 주의)
4. `docs/` - 원본 문서 (별도 백업 시)
5. `data/extracted/` - 추출 텍스트 (재생성 가능)

### 7.2 백업 실행

```bash
# DB 백업 스크립트 (권장: 주 1회)
./scripts/ops/backup_db.py

# 수동 백업
mkdir -p backups/$(date +%Y%m%d)
cp metadata.db backups/$(date +%Y%m%d)/
cp -r var/index backups/$(date +%Y%m%d)/
cp .env backups/$(date +%Y%m%d)/
```

### 7.3 복구

**백업에서 복구**:
```bash
# 1. 서비스 종료
pkill -f "uvicorn|streamlit|auto_indexer"

# 2. 백업 복원
cp backups/20251211/metadata.db metadata.db

# 3. 서비스 시작
bash start_ai_chat.sh
```

**전체 재구축 (백업 없을 때)**:
```bash
# 원본 PDF만 있으면 가능
rm metadata.db
rm -rf var/index/*
.venv/bin/python3 scripts/core/ingest_from_docs.py --source docs/
.venv/bin/python3 scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index
```

---

## 8. 트러블슈팅

### 8.1 검색이 안 될 때

```bash
# 1. 인덱스 재생성
.venv/bin/python3 scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index

# 2. Streamlit 재시작
pkill -f streamlit
streamlit run app/main.py
```

### 8.2 문서가 목록에 안 보일 때

```bash
# 1. metadata.db에 있는지 확인
./scripts/ops/list_docs.sh --search "파일명"

# 2. 없으면 다시 인제스트
cp docs/year_YYYY/파일명.pdf docs/incoming/
./scripts/ops/add_docs.sh
```

### 8.3 메타데이터가 잘못 추출됐을 때

```bash
# 수동으로 수정
./scripts/ops/set_meta.sh --id 123 --date 2024-01-15 --drafter 하승범
```

### 8.4 텍스트 추출 품질이 낮을 때

```bash
# 1. data/extracted/에서 해당 .txt 파일 직접 편집
vim data/extracted/2024-01-15_문서명.txt

# 2. 메타데이터 재추출
./scripts/ops/set_meta.sh --reparse 123

# 3. 인덱스 재생성
.venv/bin/python3 scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index
```

### 8.5 stale_index_entries > 0

```bash
# 자동 정리 대기 (10초) 또는 수동 재인덱싱
.venv/bin/python3 scripts/core/reindex_atomic.py --source ./docs --swap-to ./var/index
```

### 8.6 Mutex lock stuck

```bash
# 락 파일 확인
ls -la var/reindexing.lock

# 프로세스 확인
ps aux | grep auto_indexer

# 프로세스 없으면 락 파일 삭제
rm var/reindexing.lock
```

### 8.7 응답 시간이 느릴 때

```bash
# 검색 결과 개수 감소
SEARCH_TOP_K=3
DOC_TOPK=2

# LLM max_tokens 감소
LLM_MAX_TOKENS=1024

# GPU 사용 확인
nvidia-smi
```

### 8.8 GPU 메모리 부족

```bash
# 컨텍스트 크기 감소
N_CTX=4096

# GPU 레이어 부분 사용
N_GPU_LAYERS=20  # -1 대신 구체적 숫자
```

### 8.9 일반적인 에러 코드

| 에러 | 원인 | 해결 |
|------|------|------|
| `FileNotFoundError: metadata.db` | DB 미초기화 | `ingest_from_docs.py` 실행 |
| `database is locked` | 동시 접근 | 프로세스 종료 후 WAL 파일 삭제 |
| `CUDA out of memory` | 모델 크기 초과 | N_CTX, N_GPU_LAYERS 조정 |
| `JSONDecodeError` | 스키마 파싱 실패 | 로그 확인, 폴백 처리됨 |

---

## 9. 보안 설정

### 9.1 API 인증 (프로덕션 필수)

```bash
# .env
API_KEY=your-secret-key-here  # 32자 이상
API_KEY_HEADER=X-API-Key
```

### 9.2 네트워크 보안

```bash
# 내부 바인딩만 (외부 노출 금지)
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=7860
STREAMLIT_HOST=127.0.0.1
STREAMLIT_PORT=8501

# 외부 노출은 Nginx 리버스 프록시 + TLS 사용
```

### 9.3 레이트 리미트

```bash
RATE_LIMIT_PER_MINUTE=10
RATE_LIMIT_PER_HOUR=100
MAX_CONCURRENT_REQUESTS=4
```

### 9.4 보안 체크리스트

- [ ] API_KEY를 Git에 커밋하지 않음
- [ ] .env 파일 권한 0600
- [ ] Nginx TLS 인증서 적용
- [ ] 로그에 API_KEY 노출 방지

---

## 10. SLO 및 품질 가드

### 10.1 Service Level Objectives

| 지표 | 목표 | 경보 임계값 |
|------|------|------------|
| **p95 응답시간** | < 5초 | > 8초 |
| **RAG 인용률** | > 95% | < 80% |
| **오류율** | < 1% | > 5% |
| **인덱스 일관성** | 0 stale | > 0 |

### 10.2 품질 가드

**점수 게이팅**:
```python
# 모든 문서 점수가 RAG_MIN_SCORE 미만 → 문서근거 차단
if max(scores) < RAG_MIN_SCORE:
    if ALLOW_UNGROUNDED_CHAT:
        return chat_response()
    else:
        return "근거 없음"
```

**출처 강제**:
```bash
REQUIRE_CITATIONS=true  # RAG 모드에서 출처 누락 시 재시도
```

---

## 자주 묻는 질문

### Q: 새 문서를 추가했는데 검색이 안 돼요
A: 인덱스 재생성이 필요합니다. `add_docs.sh` 스크립트를 사용하면 자동으로 처리됩니다.

### Q: 문서를 삭제했는데 검색에 계속 나와요
A: `delete_doc.sh` 스크립트가 인덱스 재생성까지 자동으로 처리합니다.

### Q: 작성자/날짜가 "정보 없음"으로 표시돼요
A: `set_meta.sh --id 123 --drafter 하승범` 으로 수동 입력하세요.

### Q: 검토서/보고서 양식의 문서도 자동 추출되나요?
A: 네, 기안서 외에 검토서(작성자/작성일), 보고서(보고자/보고일) 양식도 지원합니다.

### Q: 원본 PDF만 있으면 복구 가능한가요?
A: 네, 원본 PDF만 있으면 나머지(텍스트, 메타데이터, 인덱스)는 모두 재생성 가능합니다.

---

## 11. 캐시 시스템

### 11.1 개요

QueryCache v2.0은 스레드 안전, 네임스페이스 분리, 캐시 스탬피드 방지를 제공하는 프로덕션 급 인메모리 캐시입니다.

**주요 기능**:
- ✅ 스레드 안전성 (threading.RLock)
- ✅ 네임스페이스 (인덱스 버전/설정 자동 반영)
- ✅ 캐시 스탬피드 방지 (in-flight de-duplication)
- ✅ TTL + LRU (만료 + 용량 기반 축출)
- ✅ Monotonic Clock (시계 변동 영향 제거)

### 11.2 기본 사용법

```python
from app.rag.cache_manager import get_cache
from app.rag.cache_namespace import current_retriever_namespace

cache = get_cache()
namespace = current_retriever_namespace()

# 캐시 조회
result = cache.get(query, mode="chat", namespace=namespace)

if result is None:
    # 캐시 미스 - 검색 수행
    result = expensive_search(query, mode="chat")
    cache.set(query, result, mode="chat", namespace=namespace)

return result
```

### 11.3 캐시 스탬피드 방지 패턴

동일 질의 동시 요청 시 중복 계산 방지:

```python
def search_with_cache(query: str, mode: str = "chat"):
    cache = get_cache()
    namespace = current_retriever_namespace()

    # 1. 캐시 조회
    result = cache.get(query, mode, namespace)
    if result is not None:
        return result

    # 2. 계산 시작 신호
    is_leader = cache.begin_inflight(query, mode, namespace)

    if is_leader:
        # 리더: 실제 검색 수행
        try:
            result = expensive_search(query, mode)
            cache.set(query, result, mode, namespace)
            return result
        finally:
            cache.end_inflight(query, mode, namespace)
    else:
        # 팔로워: 리더 대기 후 재조회
        cache.wait_inflight(query, mode, namespace, timeout=10.0)
        result = cache.get(query, mode, namespace)
        if result is None:
            result = expensive_search(query, mode)
            cache.set(query, result, mode, namespace)
        return result
```

### 11.4 네임스페이스 사용

**자동 네임스페이스** (권장):
```python
from app.rag.cache_namespace import current_retriever_namespace

# 인덱스 버전 + 설정 해시 자동 조합
namespace = current_retriever_namespace()
# 예: "bm25:v1699876543|conf:a1b2c3d4"
```

**효과**:
- 인덱스 로테이션 시 자동으로 새 캐시 키 사용
- 설정 변경 시 자동 캐시 무효화

### 11.5 통계 조회

```bash
curl -s http://localhost:7860/cache/stats | jq '.'
```

**출력 예시**:
```json
{
  "size": 45,
  "max_size": 100,
  "hits": 523,
  "misses": 177,
  "evictions": 3,
  "expired": 12,
  "hit_rate": "74.71%",
  "inflight_count": 0
}
```

### 11.6 환경 설정

```bash
# .env
CACHE_MAX_SIZE=100   # 최대 캐시 항목 수
CACHE_TTL=7200       # TTL (초, 기본 2시간)
```

### 11.7 성능 고려사항

**메모리 사용량**:
- 1개 항목: ~10KB
- 100개 항목: ~1MB

**TTL 전략**:
| 용도 | 권장 TTL |
|------|---------|
| 일반 검색 | 2시간 (7200초) |
| DOC_ANCHORED | 10분 (600초) |
| 실험/개발 | 5분 (300초) |

### 11.8 트러블슈팅

**Q: 캐시 히트율이 낮아요 (< 30%)**
- 원인: 질의 다양성 높음, 네임스페이스 자주 변경
- 해결: max_size 증가 (100 → 200), TTL 증가 (2h → 4h)

**Q: 메모리 사용량이 과다해요**
- 원인: 대형 결과 캐싱, max_size 과다
- 해결: max_size 감소 (100 → 50), TTL 감소 (2h → 1h)

---

## 12. ExactMatch 모니터링

### 12.1 개요

ExactMatchRetriever v2.0은 RAG 시스템의 Stage 0 (정확일치 단계)로, 모델번호/부품코드 질의에 대해 오검출 최소화를 최우선으로 하는 정밀 검색기입니다.

**핵심 설계 원칙**:
- 오검출 최소화 > 재현율 (False Positive 방지 최우선)
- 빠른 실패 (코드 패턴 미발견 시 즉시 BM25로 위임)
- 경계 제약 (`HRD-442` ≠ `HRD-4420`)

### 12.2 메트릭 사양

```bash
curl -s http://localhost:7860/metrics | jq '.retriever_runtime.exact_match'
```

**주요 지표**:

| 메트릭명 | 타입 | 설명 | 정상 범위 |
|---------|------|------|----------|
| `total_queries` | int | 누적 질의 수 | 증가 추세 |
| `exact_hits` | int | 코드 정확일치 건수 | - |
| `filename_hits` | int | 파일명 부분일치 건수 | - |
| `exact_match_hit_rate` | float | 정확일치 적중률 | 0.35 ~ 0.65 |
| `avg_query_time_ms` | float | 평균 검색 시간 (ms) | < 80 (p95) |

### 12.3 알람 임계치

**WARNING 레벨**:

| 조건 | 임계치 | 조치 사항 |
|-----|--------|---------|
| 낮은 적중률 | hit_rate < 0.35 | 1. 코드 패턴 확인<br>2. 정규화 로직 점검<br>3. 신규 모델번호 DB 반영 확인 |
| 높은 레이턴시 | avg_query_time_ms > 80 | 1. DB 인덱스 상태 확인<br>2. 커넥션 풀 사용률 확인 |
| 과도한 파일명 의존 | filename_hits / total_queries > 0.25 | 코드 추출 정확도 저하 의심 |

**CRITICAL 레벨**:

| 조건 | 임계치 | 조치 사항 |
|-----|--------|---------|
| 극심한 레이턴시 | avg_query_time_ms > 150 | 1. Feature Flag OFF 검토<br>2. BM25 폴백 확인 |
| API 장애 | 5xx_rate > 0.5% | 1. 롤백 준비<br>2. DB 무결성 검증 |

### 12.4 Feature Flag 제어

```bash
# .env
ENABLE_EXACT_MATCH=true   # v2.0 활성화 (기본값: true)
```

**런타임 토글** (재시작 필요):
```bash
# 비활성화
export ENABLE_EXACT_MATCH=false
pkill -f "uvicorn"
uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &

# 검증
curl -s http://localhost:7860/metrics | jq '.retriever_runtime.retriever_config'
```

### 12.5 데이터베이스 스키마

**model_codes 테이블**:
```sql
CREATE TABLE model_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    code TEXT NOT NULL,           -- 원본 코드
    norm_code TEXT NOT NULL,      -- 정규화 코드
    padded_norm TEXT,             -- 경계 제약용
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);

-- 필수 인덱스
CREATE INDEX idx_model_codes_norm ON model_codes(norm_code);
CREATE INDEX idx_model_codes_padded ON model_codes(padded_norm);
```

**인덱스 검증**:
```bash
python scripts/verify_exact_match_indexes.py
```

### 12.6 롤백 절차

**긴급 롤백** (< 5분):
```bash
# 1. Feature Flag OFF
export ENABLE_EXACT_MATCH=false
pkill -f "uvicorn"
uvicorn app.api.main:app --host 0.0.0.0 --port 7860 &

# 2. 검증
curl -s http://localhost:7860/metrics | jq '.retriever_runtime.exact_match'
# 출력: null (비활성화 확인)
```

**DB 롤백** (< 10분):
```bash
# 1. 백업 복구
cp var/metadata.db var/metadata.db.broken
cp var/backups/metadata.db.backup-YYYYMMDD var/metadata.db

# 2. 인덱스 재생성
python scripts/migrate_exact_match_indexes.py

# 3. 검증
python scripts/verify_exact_match_indexes.py
```

### 12.7 트러블슈팅

**낮은 적중률 (hit_rate < 0.35)**:
```bash
# 최근 문서의 model_codes 개수 확인
sqlite3 var/db/metadata.db "
  SELECT doc_id, COUNT(*)
  FROM model_codes
  GROUP BY doc_id
  ORDER BY id DESC
  LIMIT 10;
"
```

**높은 레이턴시 (p95 > 80ms)**:
```bash
# 인덱스 미사용 확인
python scripts/verify_exact_match_indexes.py | grep "SCAN TABLE"

# DB 공간 회수
sqlite3 var/db/metadata.db "VACUUM;"
```

---

**문서 버전**: 3.0.0 (통합본)
**마지막 업데이트**: 2025-12-25
