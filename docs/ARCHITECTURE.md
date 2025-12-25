# AI-CHAT 시스템 아키텍처

**최종 업데이트**: 2025-12-23
**시스템**: 채널A 방송 문서 RAG 시스템
**문서 수**: 475개

---

## 1. 시스템 개요

AI-CHAT은 RAG(Retrieval-Augmented Generation) 아키텍처 기반의 **채널A 방송 문서 검색 및 Q&A 시스템**입니다.

### 핵심 기능
- PDF 문서 자동 인덱싱 (pdfplumber + Tesseract OCR)
- 하이브리드 검색 (BM25 키워드 + FAISS 벡터)
- LLM 기반 질의응답 (vLLM + Qwen2.5-72B)
- 메타데이터 자동 추출 (날짜, 작성자, 카테고리)
- 쿼리 라우팅 (문서 유형별 최적화)

---

## 2. 기술 스택

| 계층 | 기술 |
|------|------|
| **프론트엔드** | Streamlit 1.38+ |
| **백엔드 API** | FastAPI + Uvicorn |
| **데이터베이스** | SQLite 3.x (WAL 모드) |
| **검색 엔진** | BM25 (키워드) + FAISS (벡터) |
| **임베딩** | intfloat/multilingual-e5-large |
| **OCR** | Tesseract 5.x |
| **LLM** | vLLM + Qwen2.5-72B-Instruct-AWQ |
| **GPU** | NVIDIA H100 80GB |
| **언어** | Python 3.12+ |

---

## 3. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         데이터 흐름 아키텍처                                   │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   원본 PDF    │  ← Source of Truth
    │  docs/year_* │     472개 PDF 파일
    └──────┬───────┘
           │
           │ (1) 텍스트 추출 (pdfplumber + OCR)
           ▼
    ┌──────────────┐
    │ 추출된 텍스트  │  ← 검색용 텍스트
    │data/extracted│     472개 .txt 파일
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
    ┌──────────────────────────────┐
    │  BM25 인덱스 + FAISS 벡터     │  ← 하이브리드 검색용
    │  rag_system/db/              │     토큰화 + 임베딩
    └──────────────────────────────┘
```

### 서비스 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│              (Streamlit Web App :8501)                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    API Layer                             │
│              (FastAPI :7860/docs)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Query    │  │ Document │  │ Metadata │              │
│  │ Endpoint │  │ Endpoint │  │ Endpoint │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  RAG Pipeline                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. Query Router (문서 유형 분류)                  │  │
│  │ 2. Hybrid Retriever (BM25 + FAISS)              │  │
│  │ 3. Context Hydrator (메타데이터 보강)            │  │
│  │ 4. LLM Generator (vLLM 답변 생성)               │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────┐
        ▼            ▼            ▼            ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ SQLite   │  │ BM25     │  │ FAISS    │  │ Extracted│
│ metadata │  │ Index    │  │ Vector   │  │ Text     │
│   .db    │  │  .pkl    │  │  .faiss  │  │  .txt    │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## 4. 디렉토리 구조

```
AI-CHAT/
├── app/                      # 핵심 애플리케이션 코드
│   ├── api/                  # FastAPI 엔드포인트
│   ├── rag/                  # RAG 파이프라인
│   │   ├── ocr/              # OCR 처리 모듈
│   │   ├── parse/            # 메타데이터 파서
│   │   ├── preprocess/       # 텍스트 전처리
│   │   └── retrievers/       # 검색기
│   ├── data/                 # 데이터 계층
│   │   └── metadata_db.py    # SQLite 인터페이스
│   └── core/                 # 공통 유틸리티
│       └── logging.py        # 로깅 설정
│
├── scripts/                  # 운영 스크립트
│   ├── core/                 # 핵심 스크립트
│   │   ├── ingest_from_docs.py   # 문서 인제스트
│   │   └── reindex_atomic.py     # 원자적 재색인
│   └── ops/                  # 운영 도구
│       ├── add_docs.sh           # 문서 추가
│       ├── delete_doc.sh         # 문서 삭제
│       ├── list_docs.sh          # 문서 목록
│       ├── set_meta.sh           # 메타데이터 수정
│       ├── healthcheck.py        # 헬스체크
│       └── backup_db.py          # DB 백업
│
├── docs/                     # 문서 저장소
│   ├── incoming/             # 신규 문서 대기
│   ├── year_2017~2025/       # 연도별 문서
│   └── quarantine/           # 삭제 문서 백업
│
├── data/
│   └── extracted/            # 추출된 텍스트 (.txt)
│
├── var/
│   ├── db/                   # 데이터베이스
│   │   ├── metadata.db       # 메타데이터 DB (SQLite)
│   │   └── everything_index.db  # Everything 인덱스
│   ├── backups/              # DB 백업
│   ├── log/                  # 로그 파일
│   └── index/                # 검색 인덱스 (레거시)
│
├── rag_system/
│   ├── db/                   # BM25/FAISS 인덱스
│   │   ├── bm25_index.pkl
│   │   └── korean_vector_index.faiss
│   └── file_index.json       # 파일 인덱스
│
├── config/
│   ├── constants.py          # 설정 상수
│   ├── query_routing_patterns.yaml  # 질의 라우팅 패턴
│   └── document_processing.yaml  # 문서 처리 설정
│
└── web_interface.py          # Streamlit 진입점
```

---

## 5. 데이터 흐름

### 5.1 문서 인제스트 (Ingestion)

```
PDF 파일 (docs/incoming/)
   │
   ▼
[PDF 텍스트 추출]
   │ ├─ pdfplumber (1차 시도)
   │ └─ Tesseract OCR (폴백)
   │
   ▼
[텍스트 저장]
   │ └─ data/extracted/*.txt
   │
   ▼
[메타데이터 파싱]
   │ ├─ 날짜 추출 (시행일자, 기안일자, 작성일, 파일명)
   │ ├─ 작성자 추출 (기안자, 작성자, 검토자, 담당자)
   │ └─ 카테고리 분류 (proposal, review, report, etc.)
   │
   ▼
[DB 저장]
   │ └─ metadata.db (documents 테이블)
   │
   ▼
[PDF 이동]
   │ └─ docs/year_YYYY/
   │
   ▼
[인덱스 빌드]
   └─ BM25 + FAISS 인덱스 (rag_system/db/)
```

### 5.2 검색 (Retrieval)

```
사용자 쿼리
   │
   ▼
[쿼리 라우팅]
   │ └─ 의도 분류 (SEARCH, DOCUMENT, QA, COST, YEAR_SUMMARY)
   │
   ▼
[하이브리드 검색]
   │ ├─ BM25 (키워드 기반, 가중치 0.8)
   │ └─ FAISS (벡터 기반, 가중치 0.2)
   │
   ▼
[메타데이터 보강]
   │ └─ 날짜, 작성자 정보 추가
   │
   ▼
[LLM 답변 생성]
   │ └─ vLLM (Qwen2.5-72B-AWQ)
   │
   ▼
응답 반환
```

---

## 6. 주요 컴포넌트

### 6.1 RAG 파이프라인 (`app/rag/pipeline.py`)
- 검색-생성 통합 오케스트레이션
- 캐싱 레이어
- 메트릭 수집

### 6.2 Query Router (`app/rag/query_router.py`)
- 쿼리 유형 분류 (SEARCH, DOCUMENT, QA, COST, YEAR_SUMMARY)
- YAML 패턴 기반 라우팅 (`config/query_routing_patterns.yaml`)

### 6.3 Hybrid Retriever (`app/rag/retrievers/hybrid.py`)
- BM25 키워드 검색 (가중치 0.8)
- FAISS 벡터 검색 (가중치 0.2)
- 한국어 토크나이저 (KiwiPy)

### 6.4 MetadataDB (`app/data/metadata_db.py`)
- SQLite WAL 모드
- 쓰레드 안전 연결 관리
- 문서 메타데이터 CRUD

### 6.5 Meta Parser (`app/rag/parse/parse_meta.py`)
- 정규식 기반 메타데이터 추출
- 날짜 정규화 (YYYY-MM-DD)
- 작성자 Stoplist 필터링

---

## 7. 인덱스 아키텍처

### 7.1 doc_id 규격

**원천 시스템**: metadata.db의 `documents.id` (INTEGER PK)

**규칙**:
- 모든 인덱스에서 `str(id)` 형식 사용
- DocStore/BM25 키 일치 필수
- 정합성 검증: `scripts/check_index_consistency.py`

### 7.2 정합성 검증

```bash
# 정합성 확인
python scripts/check_index_consistency.py

# 정상 상태
✅ 정합성 점수: 100.00%
✅ DocStore 키 = BM25 키 (완전 일치)
```

---

## 8. 데이터베이스 스키마

### documents 테이블

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,
    date TEXT,              -- YYYY-MM-DD
    year TEXT,              -- YYYY
    month TEXT,             -- YYYY-MM
    drafter TEXT,           -- 작성자
    category TEXT,          -- 카테고리
    doctype TEXT,           -- 문서 유형
    text_preview TEXT,      -- 텍스트 미리보기
    file_hash TEXT,         -- SHA1 해시
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. 성능 특성

| 지표 | 값 |
|------|-----|
| 문서 수 | 472개 |
| 인덱싱 속도 | ~5초/문서 (OCR 포함) |
| 검색 응답시간 | <500ms |
| LLM 생성시간 | ~6초 (vLLM H100) |
| DB 크기 | ~3MB |
| BM25 인덱스 | ~2MB |
| FAISS 인덱스 | ~5MB |
| VRAM 사용 | ~39GB / 80GB (49%) |

---

## 10. 관련 문서

- [운영 가이드](OPERATIONS.md) - 일상 운영, 문서 관리, 캐시, 모니터링
- [H100 완전 가이드](H100_COMPLETE_GUIDE.md) - H100 최적화, 이전, Flash Attention
- [프레젠테이션](PRESENTATION_FINAL.md) - 시스템 소개 발표 자료

---

**문서 버전**: 2.1.0
**마지막 업데이트**: 2025-12-25
