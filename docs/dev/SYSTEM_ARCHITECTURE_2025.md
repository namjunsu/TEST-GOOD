# AI-CHAT 시스템 아키텍처 (2025-11-25 최신화)

## 시스템 개요

AI-CHAT은 **채널A 방송 문서 검색 및 QA 시스템**으로, RAG(Retrieval-Augmented Generation) 아키텍처 기반의 지능형 문서 검색 플랫폼입니다.

### 핵심 기능
- 📄 **PDF 문서 자동 인덱싱** (OCR 자동 폴백)
- 🔍 **하이브리드 검색** (BM25 + FAISS 벡터 검색)
- 🤖 **LLM 기반 질의응답** (로컬 LLM 지원)
- 📊 **메타데이터 자동 추출** (날짜, 금액, 카테고리 등)
- 🎯 **쿼리 라우팅** (문서 유형별 최적화)

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| **프론트엔드** | Streamlit 1.38+ |
| **백엔드 API** | FastAPI + Uvicorn |
| **데이터베이스** | SQLite 3.x (WAL 모드) |
| **검색 엔진** | FAISS (벡터) + BM25 (키워드) |
| **OCR** | Tesseract 5.x |
| **LLM** | llama.cpp (로컬 추론) |
| **언어** | Python 3.12+ |

---

## 시스템 아키텍처

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
│  │ 2. Query Expander (동의어 확장)                  │  │
│  │ 3. Hybrid Retriever (BM25 + FAISS)               │  │
│  │ 4. Context Hydrator (메타데이터 보강)            │  │
│  │ 5. LLM Generator (답변 생성)                     │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ SQLite   │  │ FAISS    │  │ BM25     │
│ metadata │  │ Index    │  │ Index    │
│   .db    │  │  .index  │  │  .pkl    │
└──────────┘  └──────────┘  └──────────┘
```

---

## 디렉토리 구조

```
AI-CHAT/
├── app/                      # 핵심 애플리케이션 코드
│   ├── api/                  # FastAPI 엔드포인트
│   ├── rag/                  # RAG 파이프라인
│   │   ├── ocr/              # OCR 처리 모듈
│   │   ├── parse/            # 메타데이터 파서
│   │   ├── preprocess/       # 텍스트 전처리
│   │   ├── retrievers/       # 검색기 (하이브리드)
│   │   └── routing/          # 쿼리 라우팅
│   ├── data/                 # 데이터 계층
│   │   └── metadata_db.py    # SQLite 인터페이스
│   └── config/               # 설정 파일
├── scripts/                  # 운영 스크립트
│   ├── core/                 # 핵심 인덱싱 스크립트
│   │   ├── ingest_from_docs.py   # 문서 인제스트
│   │   └── reindex_atomic.py     # 원자적 재색인
│   ├── ops/                  # 운영 도구
│   │   ├── healthcheck.py        # 헬스체크
│   │   ├── backup_db.py          # DB 백업
│   │   └── ocr_reprocess.py      # OCR 재처리
│   └── deprecated/           # 레거시 스크립트 (보관)
├── docs/                     # 문서 저장소
│   ├── incoming/             # 신규 문서 입수 폴더
│   ├── year_2014/            # 연도별 문서
│   ├── year_2015/
│   └── ...
├── data/                     # 데이터 디렉토리
│   └── extracted/            # 추출된 텍스트 (.txt)
├── var/                      # 런타임 아티팩트
│   └── index/                # 검색 인덱스 (.gitignored)
├── config/                   # YAML 설정
│   └── document_processing.yaml
├── metadata.db               # 문서 메타데이터 DB
└── web_interface.py          # Streamlit 진입점
```

---

## 데이터 흐름

### 1. 문서 인제스트 (Ingestion)

```
PDF 파일
   │
   ▼
[PDF 텍스트 추출]
   │ ├─ pdfplumber (1차 시도)
   │ └─ Tesseract OCR (폴백)
   │
   ▼
[텍스트 전처리]
   │ ├─ 특수문자 제거
   │ ├─ 공백 정규화
   │ └─ 중복 라인 제거
   │
   ▼
[메타데이터 파싱]
   │ ├─ 날짜 추출 (정규식 + 휴리스틱)
   │ ├─ 금액 추출 (표 파서)
   │ ├─ 작성자/부서 추출
   │ └─ 카테고리 분류 (doctype)
   │
   ▼
[DB 저장]
   │ └─ SQLite (documents 테이블)
   │
   ▼
[인덱스 빌드]
   ├─ BM25 (키워드 검색)
   └─ FAISS (벡터 임베딩)
```

### 2. 검색 (Retrieval)

```
사용자 쿼리
   │
   ▼
[쿼리 라우팅]
   │ ├─ "DVR 구매" → equipment
   │ ├─ "예산 승인" → finance
   │ └─ "회의록" → general
   │
   ▼
[쿼리 확장]
   │ └─ 동의어 추가 (domain_synonyms.yaml)
   │
   ▼
[하이브리드 검색]
   │ ├─ BM25 (키워드 매칭)
   │ └─ FAISS (의미 유사도)
   │
   ▼
[컨텍스트 하이드레이션]
   │ └─ 메타데이터 보강 (날짜, 금액 등)
   │
   ▼
[LLM 답변 생성]
   │ └─ llama.cpp (로컬 LLM)
   │
   ▼
응답 반환
```

---

## 주요 컴포넌트

### 1. RAG 파이프라인 (`app/rag/pipeline.py`)
- 검색-생성 통합 오케스트레이션
- 캐싱 레이어 (PersistentCache)
- 메트릭 수집

### 2. Query Router (`app/rag/query_router.py`)
- 쿼리 유형 분류 (장비/재무/일반)
- 프로필 기반 매칭
- Anchor 키워드 스코어링

### 3. Hybrid Retriever (`app/rag/retrievers/hybrid.py`)
- BM25 + FAISS 병합
- 점수 정규화 및 가중치 조합
- 중복 제거

### 4. MetadataDB (`app/data/metadata_db.py`)
- SQLite WAL 모드 최적화
- FTS5 풀텍스트 검색
- 쓰레드 안전 연결 관리

### 5. OCR Pipeline (`app/rag/ocr/pipeline.py`)
- Tesseract 통합
- 이미지 전처리 (그레이스케일, 샤프닝)
- 품질 검증 (최소 문자 수)

---

## 현재 상태 (2025-11-25)

### 통계
- **총 문서**: 476개
- **문서 유형**:
  - proposal (기안서): 465개
  - review (검토서): 3개
  - report (보고서): 1개
  - disposal (폐기): 2개
  - unknown: 4개
  - pdf: 1개

### 최근 개선사항
- ✅ OCR 스크립트 통합 (9개 → 3개 카테고리)
- ✅ SQLite WAL/BM25 인덱스 .gitignore 처리
- ✅ 재난방송 문서 검색 문제 해결
- ✅ DB-파일시스템 동기화 자동화

---

## 운영 가이드

### 시스템 시작
```bash
./start_ai_chat.sh
```

### 신규 문서 추가
```bash
# 1. PDF를 incoming 폴더에 복사
cp new_doc.pdf docs/incoming/

# 2. 인제스트 실행
.venv/bin/python scripts/core/ingest_from_docs.py --ocr-mode fallback

# 3. BM25 인덱스 재빌드
.venv/bin/python scripts/quick_rebuild_bm25.py
```

### 헬스체크
```bash
.venv/bin/python scripts/ops/healthcheck.py
```

---

## 성능 특성

| 지표 | 값 |
|------|-----|
| 인덱싱 속도 | ~5초/문서 (OCR 포함) |
| 검색 응답시간 | <500ms (BM25+FAISS) |
| LLM 생성시간 | ~2-5초 (로컬 LLM) |
| DB 크기 | ~3.2MB (476개 문서) |
| 인덱스 크기 | ~1-2MB (BM25) |

---

## 보안 고려사항

- 로컬 LLM 사용 (외부 API 의존성 없음)
- SQLite WAL 파일 .gitignore 처리
- 민감 문서는 `docs/rejected/` 격리
- API 엔드포인트 인증 없음 (내부망 가정)

---

## 확장성 로드맵

### 단기 (1개월)
- [ ] FAISS 인덱스 자동 재빌드 트리거
- [ ] 문서 중복 제거 강화
- [ ] 쿼리 성능 메트릭 대시보드

### 중기 (3개월)
- [ ] PostgreSQL 마이그레이션 (SQLite 대체)
- [ ] Elasticsearch 통합 (BM25 대체)
- [ ] 멀티모달 검색 (이미지 내 텍스트)

### 장기 (6개월+)
- [ ] 클러스터링 아키텍처 (분산 검색)
- [ ] GPU 가속 벡터 검색
- [ ] 자동 분류 모델 파인튜닝

---

## 문의 및 지원

- 이슈 트래커: (내부 레포지토리)
- 문서: `docs/dev/` 디렉토리 참조
- 운영 가이드: `OPERATIONS_GUIDE.md`
