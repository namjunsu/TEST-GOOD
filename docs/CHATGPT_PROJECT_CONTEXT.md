# AI-CHAT Project Context for ChatGPT

> **목적**: ChatGPT Projects에서 AI-CHAT 시스템을 이해하고, 코드 개선, 디버깅, 기능 추가 등을 도와주기 위한 컨텍스트 문서

---

## 프로젝트 개요

**AI-CHAT**은 채널A 방송국의 **문서 검색 및 질의응답 시스템**입니다.

### 핵심 가치
- 📄 **476개 방송 문서** (기안서, 보고서 등) 자동 인덱싱
- 🔍 **하이브리드 검색**: BM25 (키워드) + FAISS (의미 유사도)
- 🤖 **로컬 LLM 기반 QA**: 외부 API 없이 자체 LLM 운영
- ⚡ **자동 OCR 폴백**: 이미지 PDF도 자동 텍스트 추출

### 기술 스택 (한눈에)
```
Python 3.12 | FastAPI | Streamlit | SQLite | FAISS | BM25 | Tesseract OCR | llama.cpp
```

---

## 현재 시스템 상태 (2025-11-25)

### 주요 지표
| 항목 | 값 |
|------|-----|
| 총 문서 수 | 476개 |
| 인덱스 크기 | ~3.2MB (DB) + ~1-2MB (BM25) |
| 평균 검색 시간 | <500ms |
| OCR 성공률 | ~98% |
| 최근 커밋 | `c3d9a50` (SQLite WAL 및 BM25 .gitignore) |

### 최근 해결한 문제
1. ✅ OCR 스크립트 중복 제거 (9개 → 3개 카테고리로 정리)
2. ✅ 재난방송 문서 검색 불가 문제 (DB 경로 불일치 해결)
3. ✅ Git 아티팩트 정리 (WAL 파일, BM25 인덱스 .gitignore)

---

## 디렉토리 구조 (핵심만)

```
AI-CHAT/
├── app/                          # 애플리케이션 코드
│   ├── api/main.py               # FastAPI 엔드포인트
│   ├── rag/                      # RAG 파이프라인
│   │   ├── pipeline.py           # 검색-생성 오케스트레이션
│   │   ├── query_router.py       # 쿼리 유형 분류 (장비/재무/일반)
│   │   ├── retrievers/hybrid.py  # BM25 + FAISS 하이브리드 검색
│   │   ├── ocr/pipeline.py       # Tesseract OCR 통합
│   │   └── parse/parse_meta.py   # 메타데이터 파서 (날짜, 금액 등)
│   └── data/metadata_db.py       # SQLite 인터페이스 (WAL 모드)
│
├── scripts/                      # 운영 스크립트
│   ├── core/                     # 핵심 인덱싱
│   │   ├── ingest_from_docs.py   # 문서 인제스트 (OCR 폴백)
│   │   └── reindex_atomic.py     # 원자적 재색인
│   ├── ops/                      # 운영 도구
│   │   ├── healthcheck.py        # 시스템 헬스체크
│   │   ├── backup_db.py          # DB 백업
│   │   └── ocr_reprocess.py      # OCR 재처리
│   └── deprecated/               # 레거시 (보관용)
│
├── docs/                         # 문서 저장소
│   ├── incoming/                 # 신규 문서 입수
│   ├── year_2014~/               # 연도별 분류
│   └── dev/                      # 개발 문서
│       ├── SYSTEM_ARCHITECTURE_2025.md
│       └── FEATURES_AND_SCRIPTS.md
│
├── config/                       # YAML 설정
│   └── document_processing.yaml  # 메타데이터 파싱 규칙
│
├── metadata.db                   # SQLite DB (문서 메타데이터)
└── web_interface.py              # Streamlit 진입점
```

---

## 핵심 컴포넌트 설명

### 1. RAG Pipeline (`app/rag/pipeline.py`)
**역할**: 사용자 쿼리 → 문서 검색 → LLM 답변 생성

**흐름**:
```
Query → Router → Expander → Retriever → Hydrator → LLM → Response
  ↓        ↓         ↓          ↓           ↓        ↓
"DVR구매" → 장비  → +동의어 → BM25+FAISS → +메타 → llama.cpp
```

**주요 메서드**:
```python
def search(query: str, top_k: int = 10) -> List[Document]
def answer(question: str, use_llm: bool = True) -> str
```

### 2. Query Router (`app/rag/query_router.py`)
**역할**: 쿼리를 `equipment`, `finance`, `general` 중 분류

**분류 기준**:
```yaml
equipment:
  anchors: ["DVR", "카메라", "구매", "렌즈"]
finance:
  anchors: ["예산", "승인", "비용", "지출"]
```

### 3. Hybrid Retriever (`app/rag/retrievers/hybrid.py`)
**역할**: BM25 + FAISS 점수 결합

**알고리즘**:
```python
final_score = 0.6 * bm25_score + 0.4 * faiss_score
```

### 4. MetadataDB (`app/data/metadata_db.py`)
**역할**: SQLite DB 래퍼 (WAL 모드, FTS5 지원)

**스키마**:
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    title TEXT,
    date TEXT,
    year TEXT,
    category TEXT,
    amount INTEGER,        -- 금액
    text_preview TEXT,     -- 미리보기 (300자)
    doctype TEXT,          -- proposal/report/review
    ...
);
```

### 5. OCR Pipeline (`app/rag/ocr/pipeline.py`)
**역할**: pdfplumber 실패 시 Tesseract OCR 폴백

**품질 체크**:
```python
if len(extracted_text) < 100:  # 100자 미만은 실패로 간주
    raise OCRError("텍스트 추출 실패")
```

---

## 일반적인 작업 시나리오

### 시나리오 1: 신규 문서 추가
```bash
# 1. PDF를 incoming에 복사
cp new_doc.pdf docs/incoming/

# 2. 인제스트 (OCR 자동 폴백)
.venv/bin/python scripts/core/ingest_from_docs.py --ocr-mode fallback

# 3. BM25 인덱스 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
```

### 시나리오 2: 검색이 안 될 때
```bash
# 1. 헬스체크
.venv/bin/python scripts/ops/healthcheck.py

# 2. 동기화 확인
.venv/bin/python scripts/ops/auto_sync_checker.py --dry-run

# 3. 인덱스 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
```

### 시나리오 3: OCR 품질 개선
```bash
# 1. Tesseract 한국어 데이터 설치
sudo apt-get install tesseract-ocr-kor

# 2. 품질 낮은 문서 재처리
.venv/bin/python scripts/ops/ocr_reprocess.py --char-threshold 100
```

---

## 자주 발생하는 문제 및 해결책

### 문제 1: "SQLite database is locked"
**원인**: 다중 프로세스에서 동시 쓰기

**해결**:
```python
# metadata_db.py에서 WAL 모드 활성화됨
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

### 문제 2: "BM25 인덱스가 오래됨"
**원인**: 문서 추가 후 인덱스 미재빌드

**해결**:
```bash
.venv/bin/python scripts/quick_rebuild_bm25.py
```

### 문제 3: "메타데이터 파싱 실패 (날짜 없음)"
**원인**: PDF 내 날짜 형식이 규칙에 없음

**해결**:
```yaml
# config/document_processing.yaml 편집
date_patterns:
  - pattern: "\\d{4}[년.-]\\d{1,2}[월.-]\\d{1,2}"
    priority: 5
  - pattern: "\\d{4}/\\d{2}/\\d{2}"  # 새 패턴 추가
    priority: 4
```

---

## 코드 컨벤션

### Python 스타일
- PEP 8 준수
- Type hints 필수 (Python 3.12+)
- Docstring: Google 스타일

```python
def process_document(pdf_path: str, ocr_mode: str = "fallback") -> Dict[str, Any]:
    """PDF 문서를 처리하여 메타데이터를 추출합니다.

    Args:
        pdf_path: PDF 파일 절대 경로
        ocr_mode: OCR 모드 (off, fallback, force)

    Returns:
        메타데이터 딕셔너리 (title, date, amount 등)

    Raises:
        FileNotFoundError: PDF 파일이 존재하지 않을 때
    """
```

### 로깅
```python
from app.core.logging import get_logger

logger = get_logger(__name__)
logger.info("문서 처리 시작: %s", pdf_path)
logger.warning("OCR 폴백 실행: %s", reason)
logger.error("처리 실패: %s", error, exc_info=True)
```

---

## 성능 최적화 팁

### 1. SQLite 최적화
```sql
-- 인덱스 추가 (app/data/metadata_db.py)
CREATE INDEX idx_year ON documents(year);
CREATE INDEX idx_category ON documents(category);

-- VACUUM (월 1회 권장)
VACUUM;
```

### 2. BM25 캐싱
```python
# app/rag/retrievers/hybrid.py
@lru_cache(maxsize=1000)
def search_bm25(query: str, top_k: int) -> List[Tuple[int, float]]:
    ...
```

### 3. 비동기 처리 (대량 인제스트)
```python
# scripts/core/ingest_from_docs.py
async def process_batch(pdfs: List[Path]) -> List[Result]:
    tasks = [process_document_async(pdf) for pdf in pdfs]
    return await asyncio.gather(*tasks)
```

---

## 테스트 전략

### 단위 테스트
```bash
pytest tests/unit/
```

**커버리지 목표**: 80%+

### 통합 테스트
```bash
pytest tests/integration/test_ingestion.py
```

### Smoke Test
```bash
.venv/bin/python scripts/smoke_test.py
```

**체크 항목**:
- DB 연결
- 검색 API 응답
- LLM 생성 성공

---

## 환경 변수 (.env)

```bash
# LLM
LLM_MODEL_PATH=models/llama-2-7b-chat.gguf
LLM_N_CTX=4096

# 데이터베이스
METADATA_DB_PATH=metadata.db

# 로깅
LOG_LEVEL=INFO
LOG_DIR=logs

# API
API_HOST=0.0.0.0
API_PORT=7860

# Streamlit
STREAMLIT_PORT=8501
```

---

## 배포 및 운영

### 서버 환경
- OS: Ubuntu 22.04 LTS
- Python: 3.12.x
- RAM: 16GB+
- Disk: 50GB+

### 프로세스 관리
```bash
# systemd 서비스 등록
sudo systemctl enable ai-chat
sudo systemctl start ai-chat
sudo systemctl status ai-chat
```

### 모니터링
```bash
# 로그 모니터링
tail -f logs/app.log

# 리소스 모니터링
htop
df -h
```

---

## 추가 학습 자료

1. **시스템 아키텍처**: `docs/dev/SYSTEM_ARCHITECTURE_2025.md`
2. **기능 가이드**: `docs/dev/FEATURES_AND_SCRIPTS.md`
3. **운영 가이드**: `OPERATIONS_GUIDE.md`
4. **OCR 가이드**: `docs/dev/OCR_UPGRADE_GUIDE.md`
5. **API 문서**: http://localhost:7860/docs (Swagger)

---

## ChatGPT에게 요청할 수 있는 작업 예시

### 코드 개선
- "BM25 검색 성능을 개선하려면 어떻게 해야 할까요?"
- "OCR 품질을 높이기 위한 전처리 방법을 제안해주세요"
- "메타데이터 파서의 날짜 추출 정확도를 높이려면?"

### 디버깅
- "SQLite WAL 파일이 계속 커지는 이유를 찾아주세요"
- "특정 문서가 검색 안 되는 이유를 진단해주세요"
- "OCR이 실패하는 PDF의 공통 패턴을 분석해주세요"

### 기능 추가
- "문서 자동 분류 기능을 추가하려면 어떤 구조가 필요할까요?"
- "Elasticsearch로 마이그레이션하는 단계를 설계해주세요"
- "문서 중복 제거 알고리즘을 개선해주세요"

### 문서화
- "신규 개발자 온보딩 가이드를 작성해주세요"
- "API 사용 예제를 더 추가해주세요"
- "트러블슈팅 가이드를 업데이트해주세요"

---

## 중요한 제약사항 및 가정

1. **로컬 환경**: 외부 API 의존성 없음 (LLM, OCR 모두 로컬)
2. **단일 서버**: 분산 환경 미지원 (향후 확장 계획)
3. **SQLite 한계**: 동시 쓰기 제한 (WAL 모드로 완화)
4. **한국어 중심**: Tesseract 한국어 최적화
5. **방송 도메인**: 특수 용어 (DVR, ENG, 기안서 등) 고려

---

**마지막 업데이트**: 2025-11-25
**버전**: v2.0 (OCR 통합 완료)
**담당자**: 내부 팀
