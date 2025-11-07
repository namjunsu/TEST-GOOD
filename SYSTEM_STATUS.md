# AI-CHAT RAG 시스템 현황

**최종 업데이트**: 2025-11-07 (QueryMode 구조 재설계 + 데드 코드 정리 완료)

## 시스템 개요

채널A 방송 장비 및 시설 관련 문서 검색을 위한 RAG (Retrieval-Augmented Generation) 시스템

---

## 최근 주요 변경사항 (2025-11-07)

### 코드 정리: 데드 코드 제거 (911줄 삭제)

**목적**: QueryMode 리팩토링 후 사용되지 않는 레거시 코드 제거로 유지보수성 개선

**변경 사항**:
- `app/rag/pipeline.py`: 3,027줄 → 2,116줄 (30% 감소)
- 메서드 수: 35개 → 32개

**제거된 코드**:
1. **if False 블록** (181줄) - PREVIEW 모드로 통합된 구 파일명 요약 패턴
2. **주석 처리된 레거시 코드** (19줄) - 미구현된 기안자 검색 로직
3. **_answer_list() 메서드** (158줄) - LIST 모드가 SEARCH로 통합됨
4. **_answer_preview() 메서드** (127줄) - PREVIEW 모드가 DOCUMENT로 통합됨
5. **_answer_summary() 메서드** (426줄) - SUMMARY 모드가 DOCUMENT로 통합됨

**효과**:
- 유지보수 부담 감소 (불필요한 코드 30% 제거)
- 모드 구조 단순화와 일관성 확보
- 코드베이스 복잡도 감소

### QueryMode 구조 재설계 (8개 → 4개)

**문제점 발견**:
- DOC_ANCHORED 모드가 5개 필드만 추출 (model, manufacturer, ip_address, reason, duration_years)
- "미러클랩 카메라 삼각대 기술검토서 이문서 내용 알려줘" 쿼리 시 전체 내용 대신 제조사/모델/사유만 반환
- 실제 문서에 포함된 가격 비교 (820,000원 vs 408,000원), 기술 검토 상세 내용 등이 누락됨

**근본 원인**:
- 8개 모드 구조에서 역할 중복 및 과잉 세분화
- DOC_ANCHORED가 사용자 의도("내용 알려줘")를 무시하고 구조화된 필드만 추출

**해결 방법**:
모드 수 8개 → 4개로 단순화, DOC_ANCHORED 제거

| 구분 | 이전 (8개 모드) | 현재 (4개 모드) | 변경 사항 |
|------|----------------|----------------|----------|
| 비용 조회 | COST_SUM | **COST** | 이름만 변경 |
| 문서 내용 | DOC_ANCHORED | **삭제** | 5-field 추출의 근본 문제 |
| 문서 내용/요약 | PREVIEW, SUMMARY | **DOCUMENT** | 통합 (전체 내용 반환) |
| 문서 검색 | LIST, SEARCH, LIST_FIRST | **SEARCH** | 통합 |
| 일반 질의 | QA | **QA** | 유지 |

**변경된 파일**:
- `app/rag/query_router.py`: QueryMode enum 4개로 단순화, classify_mode() 로직 업데이트
- `app/rag/pipeline.py`: DOC_ANCHORED 핸들러 삭제 (111 lines), _answer_document() 새로 생성

**검증 결과**:
```
쿼리: "미러클랩 카메라 삼각대 기술검토서 이문서 내용 알려줘"
- 모드: DOCUMENT
- 반환 텍스트: 3,683자 (이전: ~200자)
- 가격 정보 포함: ✅ (820,000원, 408,000원)
- 제품 비교 포함: ✅ (Leofoto, COMAN)
```

**효과**:
- 사용자가 요청한 전체 문서 내용을 빠짐없이 제공
- 모드 분류 로직 단순화로 유지보수성 개선
- 과도한 구조화 대신 원문 그대로 제공

---

## 현재 데이터 현황

### 원본 문서
- **위치**: `docs/`
- **파일 수**: 474개 PDF
- **구성**: 방송 장비 결재 문서, 시설 관리 문서, 구매 검토서 등

### 추출된 텍스트
- **위치**: `data/extracted/`
- **파일 수**: 476개 TXT
- **상태**: OCR 처리 완료, URL 노이즈 제거 완료

---

## 검색 인덱스 상태

### BM25 키워드 인덱스
- **위치**: `var/index/bm25_index.pkl`
- **버전**: `v20251107143839_c8569a`
- **크기**: 2.3MB
- **문서 수**: 472개
- **마지막 재구축**: 2025-11-07 14:38

### 메타데이터 DB
- **위치**: `metadata.db`
- **크기**: 3.1MB
- **내용**: 문서 메타데이터, 청크 정보

---

## 시스템 구조

### 핵심 컴포넌트

**1. FastAPI 백엔드** (`app/api/main.py`)
- 포트: 7860
- 질의 처리 엔드포인트
- 문서 검색 API

**2. Streamlit 프론트엔드** (`web_interface.py`)
- 포트: 8501
- 사용자 인터페이스
- 문서 미리보기 기능

**3. RAG 파이프라인** (`app/rag/pipeline.py`)
- Hybrid Retriever (BM25 + Vector)
- 로컬 LLM 통합
- 컨텍스트 생성 및 답변 생성

**4. 하이브리드 검색** (`app/rag/retrievers/hybrid.py`)
- BM25 키워드 검색
- 벡터 유사도 검색
- 필터링 로직 (DOC_ANCHORED, LOW_CONF 등)

### 주요 스크립트

**인덱싱**
- `scripts/reindex_atomic.py` - 안전한 원자적 인덱스 재구축
- 기존 인덱스 백업 후 새 인덱스로 교체

**텍스트 추출**
- `utils/document_loader.py` - PDF 텍스트 추출
- `rag_system/enhanced_ocr_processor.py` - OCR 처리

**서비스 시작**
- `start_ai_chat.sh` - 통합 시작 스크립트
- FastAPI + Streamlit 자동 시작
- 인덱스 일관성 검사

---

## 운영 프로세스

### 1. 시스템 시작
```bash
bash start_ai_chat.sh
```
- 자동으로 인덱스 일관성 검사
- 필요 시 자동 재인덱싱
- FastAPI (7860) + Streamlit (8501) 시작

### 2. 새 문서 추가
1. PDF 파일을 `docs/` 또는 `docs/incoming/` 에 배치
2. 시스템이 자동으로 감지 및 처리 (start_ai_chat.sh 실행 시)
3. 또는 수동 재인덱싱: `python scripts/reindex_atomic.py`

### 3. 인덱스 재구축 (수동)
```bash
python scripts/reindex_atomic.py
```
- 모든 PDF에서 텍스트 재추출
- BM25 인덱스 재구축
- 원자적 교체 (다운타임 없음)

### 4. 서비스 재시작
```bash
pkill -f "uvicorn|streamlit" || true
bash start_ai_chat.sh
```

---

## 주요 설정 파일

### `app/config/settings.py`
- 프로젝트 루트, 데이터 경로 설정
- 데이터베이스 경로
- RAG 모델 설정

### `.env` (환경 변수)
- `DOCS_DIR` - 문서 경로
- `DATA_DIR` - 데이터 디렉토리
- `STREAMLIT_PORT` - UI 포트
- `RAG_MODEL` - LLM 모델 경로

---

## 데이터 처리 이력

### 텍스트 추출 품질 개선 (2025-11-07)
- 복잡한 표 구조의 PDF에서 텍스트 추출 실패 발견
- EnhancedOCRProcessor를 사용해 OCR 재처리
- 96개 파일 복구 완료

### URL 노이즈 제거 (2025-11-07)
- 그룹웨어 URL 패턴 (`gw.channela-mt.com/groupware/...`) 제거
- 107개 파일에서 684개 URL 제거
- 문서 내용은 보존

### BM25 인덱스 재구축 (2025-11-07)
- 정리된 텍스트 기반으로 인덱스 재구축
- 472개 문서 인덱싱 완료
- 버전: `v20251107143839_c8569a`

---

## 중요 참고 사항

### 인덱스 일관성
- `start_ai_chat.sh` 실행 시 자동으로 일관성 검사
- 인덱스와 실제 파일 상태 불일치 감지 시 자동 재인덱싱
- 수동 재인덱싱 필요 시 `scripts/reindex_atomic.py` 사용

### OCR 처리
- **올바른 메서드**: `EnhancedOCRProcessor.extract_text_with_ocr(pdf_path)`
  - 반환값: `(text: str, metadata: dict)`
- pdfplumber로 실패한 PDF는 자동으로 OCR 폴백

### 필터링 로직
- `DOC_ANCHORED`: 특정 키워드로 문서 고정 검색 (DVR, 카메라, 장비 등)
- `LOW_CONF`: 낮은 신뢰도 답변 감지 및 경고
- `HIGH_CONF`: 고신뢰도 답변 직접 반환

---

## 모니터링 포인트

### 로그 위치
- FastAPI: `logs/start_*.log` 또는 stdout
- Streamlit: 터미널 출력
- 재인덱싱: `var/last_reindex.txt`

### 주요 지표
- 인덱스 버전: `var/index_version.txt`
- 문서 수: `find docs -name "*.pdf" | wc -l`
- 인덱스 크기: `ls -lh var/index/bm25_index.pkl`

### 건강 체크
```bash
# 서비스 실행 확인
ps aux | grep -E "uvicorn|streamlit"

# 포트 확인
ss -tulpn | grep -E "7860|8501"

# 인덱스 상태
cat var/index_version.txt
```

---

## 문제 해결

### 1. 서비스가 시작되지 않을 때
- 로그 확인: `tail -50 logs/start_*.log`
- 포트 충돌 확인: `ss -tulpn | grep -E "7860|8501"`
- 잠금 파일 제거: `rm -f var/run/ai-chat.lock`

### 2. 검색 결과가 이상할 때
- 인덱스 버전 확인: `cat var/index_version.txt`
- 수동 재인덱싱: `python scripts/reindex_atomic.py`

### 3. 새 문서가 검색되지 않을 때
- `docs/` 에 PDF 파일이 있는지 확인
- 서비스 재시작: `bash start_ai_chat.sh`
- 또는 수동 재인덱싱

---

## 시스템 상태 요약

**현재 상태**: 정상 운영 중

- 문서 인덱싱: 완료 (472개 문서)
- 텍스트 품질: 양호 (OCR 처리 완료)
- 검색 인덱스: 최신 (2025-11-07 14:38)
- URL 노이즈: 제거 완료
- 서비스 구성: FastAPI + Streamlit

**다음 작업 필요 시**:
1. 새 문서 추가 → `docs/` 에 PDF 배치 후 `bash start_ai_chat.sh`
2. 텍스트 품질 문제 발견 → OCR 재처리 필요 (별도 스크립트 작성)
3. 인덱스 문제 → `python scripts/reindex_atomic.py` 실행

---

**참고**: 이 파일은 시스템 변경 시 반드시 업데이트할 것
