# 🔴 AI-CHAT 시스템 현황 완전 기록
**작성일**: 2025-01-24 21:15
**작성자**: Claude
**목적**: 시스템 전체 상태 완전 파악 및 기록

---

## 📌 핵심 요약
- **시스템**: 한국어 방송장비 문서 RAG 시스템
- **모드**: **문서 검색 모드만** (Asset 모드는 2025-01-24 완전 제거됨)
- **모델**: Qwen2.5-7B (GPU 가속 활성화)
- **문서**: 480개 PDF 파일 (docs/ 폴더)
- **정리 완료**: 2025-01-24 대대적인 파일 정리 (65개→43개 항목)

---

## 🚨 중요 기록 - 절대 잊지 말 것

### 1. ❌ ASSET 모드는 완전히 제거됨 (2025-01-24)
- 사용자 요청으로 Asset 모드 관련 코드 모두 삭제
- 장비 현황, 자산 검색 기능 없음
- **오직 PDF 문서 검색만 가능**

### 2. ✅ 현재 작동하는 기능
- PDF 문서 검색 및 요약
- LLM 기반 답변 생성
- 캐싱 시스템 (동일 질문 0초 응답)

### 3. ⚠️ 알려진 문제
- 첫 질문 시 모델 로딩 8-10초 소요
- 이후 질문도 40-60초 소요 (정상)

---

## 📂 파일별 상세 기능

### 1. **web_interface.py** (80,709 bytes)
- **역할**: Streamlit 웹 인터페이스
- **기능**:
  - 사용자 질문 입력 UI
  - 답변 표시
  - 자동 인덱서 통합
- **포트**: 8501

### 2. **perfect_rag.py** (213,173 bytes) ⭐ 핵심
- **역할**: RAG 시스템 핵심 엔진
- **주요 클래스**: `PerfectRAG`
- **주요 메서드**:
  - `answer()`: 질문 답변 (캐싱 포함)
  - `find_best_document()`: 최적 문서 찾기
  - `_generate_llm_summary()`: LLM 답변 생성
  - `_classify_search_intent()`: 항상 'document' 반환 (Asset 제거됨)
- **제거된 기능**:
  - ~~Asset 모드~~
  - ~~장비 검색~~
  - ~~_enhance_asset_response~~

### 3. **config.py** (9,651 bytes)
- **역할**: 시스템 설정
- **주요 설정**:
  ```python
  N_THREADS = 20          # CPU 24코어 활용
  N_GPU_LAYERS = -1       # 모든 레이어 GPU 사용
  N_CTX = 16384          # 컨텍스트 크기
  N_BATCH = 1024         # 배치 크기
  PARALLEL_WORKERS = 12   # 병렬 워커
  LOW_VRAM = False       # RTX 4000 16GB 활용
  ```

### 4. **auto_indexer.py** (20,716 bytes)
- **역할**: 자동 문서 인덱싱
- **기능**:
  - 60초마다 docs 폴더 모니터링
  - 새 파일 자동 인덱싱
  - 변경/삭제 감지

### 5. **log_system.py** (21,127 bytes)
- **역할**: 로깅 시스템
- **주요 클래스**: `ChatLogger`
- **메서드**:
  - `log_query()`: 질문/답변 기록
  - `log_error()`: 에러 로깅
  - `info()`, `debug()`, `warning()`, `error()`: 호환성 메서드

### 6. **response_formatter.py** (33,144 bytes)
- **역할**: 응답 포맷팅
- **기능**: Markdown 형식 답변 생성

### 7. **smart_search_enhancer.py** (18,761 bytes)
- **역할**: 검색 품질 개선
- **기능**: 동의어, 패턴 학습

---

## 📁 RAG 시스템 모듈 (rag_system/)

### 핵심 모듈:
- **qwen_llm.py**: Qwen2.5-7B 모델 인터페이스
  - GPU 가속 설정 (Flash Attention 활성화)
  - `generate_response()`: 답변 생성

- **llm_singleton.py**: LLM 싱글톤 패턴 (메모리 절약)

- **hybrid_search.py**: BM25 + Vector 하이브리드 검색

- **korean_vector_store.py**: 한국어 벡터 저장소

- **bm25_store.py**: BM25 검색 엔진

---

## 🗂️ 문서 구조 (docs/)

```
docs/
├── year_2014/ ~ year_2025/  # 연도별 폴더 (480개 고유 문서)
├── category_*/              # 카테고리 폴더 (중복 복사본)
├── recent/                  # 최근 문서
└── archive/                 # 구 문서
```

---

## 💾 시스템 사양

- **CPU**: Intel Ultra 9 285HX (24코어)
- **GPU**: RTX PRO 4000 16GB VRAM
- **RAM**: 7.5GB (WSL2 할당)
- **OS**: WSL2 Ubuntu 22.04
- **Python**: 3.10.12

---

## 🐳 Docker 구성 (준비됨, 미사용 중)

### Docker 파일 구조:
- **Dockerfile**: 2단계 빌드 (초경량 이미지 목표 10GB)
  - Stage 1: Python 패키지 빌드
  - Stage 2: CUDA 12.1 기반 실행 환경
  - Tesseract OCR 포함
  - 모델/문서는 볼륨 마운트로 처리

- **docker-compose.yml**:
  - 메인 서비스: `rag-system` (GPU 지원)
  - 추가 서비스: Redis, Prometheus, Grafana (선택사항)
  - 볼륨: models, docs, cache, indexes
  - 포트: 8501 (메인), 8502 (대시보드), 6379 (Redis), 9090 (Prometheus), 3000 (Grafana)

- **Dockerfile.optimized**: 최적화된 버전
- **.dockerignore**: 모델/문서 제외 (볼륨 마운트용)

### Docker 상태:
- **Docker 데몬**: 실행 중
- **컨테이너**: 없음 (현재 직접 실행 중)
- **이미지**: 미빌드

### Docker 실행 방법:
```bash
# 이미지 빌드
docker-compose build

# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f rag-system
```

**주의**: 현재는 Docker 없이 직접 실행 중

---

## 🔥 현재 프로세스 상태

- **실행 방식**: 직접 실행 (Docker 미사용)
- **Streamlit**: 포트 8501에서 실행 중
- **GPU 사용**: 5.8GB / 16GB VRAM 사용 중
- **모델**: Qwen2.5-7B GPU 로드 완료

---

## ⚠️ 주의사항 및 기억해야 할 것

1. **Asset 모드는 완전히 제거됨** - 다시 요청하지 말 것
2. **문서 검색만 가능** - 장비 수량, 현황 등은 PDF에서만 찾음
3. **첫 로딩 8-10초는 정상** - GPU 모델 로딩 시간
4. **캐싱 작동 중** - 동일 질문은 즉시 응답

---

## 📝 변경 이력

### 2025-01-24
- ✅ ChatLogger 오류 수정
- ✅ _classify_search_intent return 문 수정
- ✅ __del__ 메서드 오류 수정
- ✅ GPU/CPU 최적화 설정
- ❌ **Asset 모드 완전 제거** (사용자 요청)
- 🧹 **대대적인 파일 정리 완료**:
  - 불필요한 파일 22개+ 삭제
  - 백업 폴더 통합 (backup/, backup_legacy/ → archive/all_backups/)
  - 중복 RAG 모듈 제거 (rag_core/, rag_modules/)
  - 테스트/모니터링 폴더 제거
  - 65개 항목 → 43개로 정리

### 이전
- 시스템 초기 구축
- 문서 인덱싱 시스템 구현
- LLM 통합

---

## 🎯 현재 시스템 요약

**이 시스템은 PDF 문서 검색 전용 RAG 시스템입니다.**
- 질문 → PDF 검색 → LLM 답변 생성
- Asset/장비 데이터베이스 기능 없음
- 480개 PDF 문서만 검색 가능

---

**끝**