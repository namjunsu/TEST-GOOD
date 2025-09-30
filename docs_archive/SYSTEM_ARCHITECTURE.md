# AI-CHAT 시스템 아키텍처 문서
*최종 업데이트: 2025-09-29*

## 📋 개요
AI-CHAT은 한국어 PDF 문서 검색 및 질의응답을 위한 RAG(Retrieval-Augmented Generation) 시스템입니다.

## 🏗️ 시스템 구조

### 1. 핵심 실행 흐름
```
사용자 → web_interface.py (Streamlit UI)
       → perfect_rag.py (메인 RAG 엔진)
       → rag_system/ (AI 모듈들)
       → 검색 결과 + AI 응답
```

## 📁 디렉토리 구조

```
AI-CHAT/
│
├── 🎯 핵심 실행 파일
│   ├── web_interface.py (80KB)      # Streamlit 웹 인터페이스
│   └── perfect_rag.py (233KB)       # 통합 RAG 시스템 (⚠️ 리팩토링 필요)
│
├── 📦 핵심 모듈
│   ├── config.py                    # 시스템 설정
│   ├── everything_like_search.py    # 초고속 파일 검색
│   ├── metadata_extractor.py        # PDF 메타데이터 추출
│   ├── metadata_db.py               # 메타데이터 DB 관리
│   ├── log_system.py                # 로깅 시스템
│   ├── response_formatter.py        # 응답 포맷팅
│   ├── auto_indexer.py              # 자동 인덱싱
│   ├── enhanced_cache.py            # 캐시 시스템
│   └── ocr_processor.py             # OCR 처리
│
├── 📚 데이터 디렉토리
│   ├── docs/ (341MB)                # PDF 문서들
│   ├── models/ (5.7GB)              # Qwen 2.5 7B AI 모델
│   ├── config/                      # 설정 파일들
│   ├── logs/ (120MB)                # 시스템 로그
│   └── cache/                       # 캐시 파일들
│
├── 🔧 시스템 디렉토리
│   ├── rag_system/ (38MB)           # RAG 시스템 모듈들
│   │   ├── qwen_llm.py              # LLM 핸들러
│   │   ├── korean_vector_store.py   # 한국어 벡터 저장소
│   │   ├── hybrid_search.py         # 하이브리드 검색
│   │   └── [기타 13개 모듈]
│   └── venv/ (446MB)                # Python 가상환경
│
├── 🧪 테스트 디렉토리
│   └── tests/                       # 테스트 파일들
│
└── 🗑️ 아카이브 (삭제 가능)
    └── old_backups/ (26MB)          # 백업 및 사용 안되는 파일들

```

## 🔑 주요 기능

### 1. 문서 검색
- **Everything-like 검색**: SQLite 기반 초고속 파일 검색
- **한국어 날짜 변환**: "2024년 8월" → "2024-08" 자동 변환
- **메타데이터 추출**: 날짜, 금액, 부서, 문서 유형 자동 추출

### 2. AI 응답 생성
- **모델**: Qwen 2.5 7B (4.4GB GGUF 형식)
- **한국어 최적화**: 한국어 문서 이해 및 응답 생성
- **컨텍스트 기반**: 검색된 문서를 기반으로 정확한 답변 생성

### 3. 웹 인터페이스
- **Streamlit 기반**: 직관적인 웹 UI
- **실시간 검색**: 빠른 문서 검색 및 답변 생성
- **문서 관리**: 문서 목록 보기, 검색, 필터링

## ⚠️ 알려진 문제점

### 1. perfect_rag.py 거대화
- **문제**: 5,378줄, 233KB의 거대한 단일 파일
- **영향**: 유지보수 어려움, 코드 가독성 저하
- **해결방안**: 기능별 모듈 분리 필요

### 2. 중복 코드
- 여러 파일에서 유사한 기능 중복 구현
- 캐싱, 로깅 등이 여러 곳에서 독립적으로 구현됨

## 🚀 실행 방법

### 1. 환경 설정
```bash
source venv/bin/activate
```

### 2. 웹 인터페이스 실행
```bash
streamlit run web_interface.py
# 또는
./start_ai_chat.sh
```

### 3. 브라우저 접속
```
http://localhost:8501
```

## 📊 시스템 통계

- **총 Python 파일**: 12개 (루트)
- **총 코드 라인**: 약 15,000줄
- **문서 개수**: 480개 PDF
- **시스템 크기**: 약 6.3GB (모델 포함)
- **평균 응답 시간**: 0.2초 (검색), 5-30초 (AI 응답)

## 🔧 개선 계획

1. **perfect_rag.py 리팩토링**
   - 클래스별 분리
   - 기능별 모듈화
   - 테스트 코드 추가

2. **성능 최적화**
   - 캐싱 전략 개선
   - 인덱싱 최적화
   - 메모리 사용량 감소

3. **코드 정리**
   - 중복 코드 제거
   - 명확한 모듈 경계 설정
   - 문서화 강화

## 📝 참고사항

- `old_backups/` 디렉토리는 확인 후 삭제 가능 (26MB 절약)
- `.gitignore`에 불필요한 파일들 추가 필요
- 정기적인 로그 파일 정리 필요 (logs/ 120MB)