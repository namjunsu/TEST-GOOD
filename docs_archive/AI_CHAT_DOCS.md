# AI-CHAT RAG System 통합 문서
> 작성일: 2025-01-26
> 통합본: 15개 MD 파일을 하나로 정리

## 📌 목차
1. [시스템 개요](#시스템-개요)
2. [시스템 사양](#시스템-사양)
3. [현재 상태](#현재-상태)
4. [설치 및 실행](#설치-및-실행)
5. [마이그레이션 가이드](#마이그레이션-가이드)
6. [개발 로드맵](#개발-로드맵)

---

## 시스템 개요

### 프로젝트 정보
- **이름**: AI-CHAT RAG System
- **목적**: 방송기술팀 문서 검색 시스템
- **문서**: 480개 PDF (2014-2025년)
- **상태**: 운영 중 (가짜 RAG, 개선 필요)

### 핵심 기능
- PDF 문서 검색 (파일명 기반)
- Qwen2.5-7B LLM 답변 생성
- 자동 인덱싱 (60초 주기)
- 웹 인터페이스 (Streamlit)

---

## 시스템 사양

### 하드웨어
- **CPU**: Intel Ultra 9 185H (24코어)
- **RAM**: 32GB DDR5
- **GPU**: RTX 4000 Ada 16GB
- **SSD**: 1TB NVMe

### 소프트웨어
- **OS**: Ubuntu 22.04 (WSL2)
- **Python**: 3.10
- **CUDA**: 12.1
- **주요 라이브러리**: Streamlit, llama-cpp-python, pdfplumber

---

## 현재 상태

### 파일 구조 (2025-01-26 정리 완료)
```
총 10개 핵심 Python 파일:
- web_interface.py      # 웹 UI
- perfect_rag.py        # RAG 엔진
- config.py             # 설정
- log_system.py         # 로깅
- metadata_db.py        # SQLite DB
- content_search.py     # PDF 검색
- response_formatter.py # 응답 포맷
- auto_indexer.py       # 자동 인덱싱
- multi_doc_search.py   # 다중 문서
- index_builder.py      # 인덱스 구축
```

### 문서 현황
- **총 PDF**: 480개
- **텍스트 추출 가능**: 60% (288개)
- **스캔 PDF (OCR 필요)**: 40% (192개)
- **OCR 캐시**: 878KB (.ocr_cache.json)

### 성능 지표
- 초기 로딩: 30초
- 검색 응답: 5-10초
- 검색 정확도: 약 48% (파일명 매칭만)
- 메모리 사용: 14GB (LLM 로드 시)

### 문제점
1. **가짜 RAG**: 실제 임베딩/벡터 검색 없음
2. **파일명 의존**: 내용 검색 불가
3. **스캔 PDF**: 40% 문서 검색 불가
4. **확장성 부족**: 문서 증가 시 성능 저하

---

## 설치 및 실행

### 1. 기본 실행
```bash
# 1. 환경 설정
cd /home/wnstn4647/AI-CHAT
source .env

# 2. Streamlit 실행
streamlit run web_interface.py

# 3. 웹 브라우저 접속
http://localhost:8501
```

### 2. Docker 실행 (GPU 지원)
```bash
# 이미지 빌드
docker build -t ai-chat .

# 컨테이너 실행
docker run --gpus all -p 8501:8501 \
  -v $(pwd)/docs:/app/docs \
  -v $(pwd)/models:/app/models \
  ai-chat
```

### 3. 초보자용 실행
```bash
# 자동 시작 스크립트
./start_ai_chat.sh
```

---

## 마이그레이션 가이드

### 다른 PC로 이전
```bash
# 1. 백업 생성
tar -czf ai_chat_backup.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.log' \
  /home/wnstn4647/AI-CHAT

# 2. 새 PC에서 복원
tar -xzf ai_chat_backup.tar.gz
cd AI-CHAT

# 3. 의존성 설치
pip install -r requirements_updated.txt

# 4. 실행
streamlit run web_interface.py
```

### 필수 이전 항목
- `docs/` - 모든 PDF 문서
- `models/` - Qwen2.5-7B 모델
- `.env` - 환경 설정
- `.ocr_cache.json` - OCR 캐시

---

## 개발 로드맵

### Phase 0: 정리 (완료 ✅)
- 불필요 파일 제거 (161→10개)
- 문서화 통합
- 구조 개선

### Phase 1: OCR 활성화 (1일)
- 192개 스캔 PDF 처리
- Tesseract OCR 적용
- 캐시 시스템 구축

### Phase 2: 내용 검색 (2일)
- PDF 내용 기반 검색
- BM25 스코어링
- 메타데이터 DB 활용

### Phase 3: 진짜 RAG (5일)
- 문서 청킹 (500토큰)
- 임베딩 생성 (sentence-transformers)
- 벡터 DB (FAISS/ChromaDB)
- 하이브리드 검색

### 예상 개선 효과
| 지표 | 현재 | 목표 |
|------|------|------|
| 검색 가능 문서 | 60% | 100% |
| 검색 정확도 | 48% | 85%+ |
| 응답 속도 | 30초 | 3초 |
| 메모리 사용 | 14GB | 8GB |

---

## 정리 완료 파일

### 삭제/이동된 MD 파일
다음 개별 MD 파일들은 이 통합 문서에 포함되어 삭제 가능:
- CLAUDE.md (프로젝트 구조)
- README.md (기본 설명)
- SYSTEM_SPECS.md (시스템 사양)
- CURRENT_SYSTEM_STATUS.md (현재 상태)
- PROJECT_STATUS.md (프로젝트 상태)
- RAG_ROADMAP.md (개발 로드맵)
- MIGRATION_GUIDE.md (마이그레이션)
- DOCKER_MIGRATION_SIMPLE.md (Docker 가이드)
- 초보자_실행_가이드.md (실행 가이드)
- 초보자_이전_가이드.md (이전 가이드)
- CLEANUP_*.md (정리 관련 3개)
- SYSTEM_FLOW_EXPLANATION.md (시스템 플로우)

### 유지 파일
- **AI_CHAT_DOCS.md** (이 파일 - 통합 문서)

---

## 연락처 및 지원
- 시스템 관련 문의: 방송기술팀
- 최종 업데이트: 2025-01-26