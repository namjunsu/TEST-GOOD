# 📁 AI-CHAT RAG System - 폴더 구조 가이드

## 🏗️ 프로젝트 구조 (2025-10-23 정리 완료)

```
AI-CHAT/
├── 📂 src/                        # 🔥 핵심 소스 코드
│   ├── web_interface.py            # 메인 Streamlit 웹 인터페이스
│   ├── config.py                   # 시스템 설정
│   ├── quick_fix_rag.py            # RAG 빠른 실행 모듈
│   ├── hybrid_chat_rag_v2.py       # 하이브리드 검색 통합 모듈
│   ├── everything_like_search.py   # Everything 스타일 검색
│   └── components/                 # UI 컴포넌트
│       ├── chat.py
│       ├── pdf_viewer.py
│       └── sidebar.py
│
├── 📂 rag_system/                  # RAG 시스템 코어
│   ├── hybrid_search.py           # 하이브리드 검색 엔진
│   ├── korean_vector_store.py     # 한국어 벡터 스토어
│   ├── bm25_store.py              # BM25 검색 스토어
│   ├── korean_reranker.py        # 한국어 재순위화
│   ├── qwen_llm.py               # Qwen LLM 모듈
│   └── ...
│
├── 📂 data/                       # 데이터 저장소
│   ├── databases/                 # DB 파일
│   │   ├── everything_index.db   # 검색 인덱스 DB
│   │   └── metadata.db           # 메타데이터 DB
│   ├── ocr_cache/                # OCR 캐시 데이터
│   ├── indexes/                  # 검색 인덱스
│   └── models/                   # 임베딩 모델 캐시
│
├── 📂 modules/                    # 보조 모듈
├── 📂 utils/                      # 유틸리티
├── 📂 services/                   # 서비스 컴포넌트
├── 📂 static/                     # 정적 파일
│   └── images/                   # 이미지 리소스
│
├── 📂 deployment/                 # 배포 스크립트
│   ├── docker/                   # Docker 설정
│   ├── scripts/                  # Shell 스크립트
│   └── windows/                  # Windows 스크립트
│
├── 📂 docs/                      # PDF 문서 (실제 검색 대상)
├── 📂 archive/                   # 보관 파일
│   ├── backups/                 # 백업 파일
│   ├── old_scripts/            # 이전 버전 스크립트
│   └── documentation/          # 프로젝트 문서
│
├── 📄 start_ai_chat.sh          # 🚀 메인 실행 스크립트
├── 📄 run_rag.sh               # 간단 실행 스크립트
├── 📄 config.py                # 루트 설정 (호환성)
├── 📄 requirements.txt         # Python 의존성
└── 📄 README.md               # 프로젝트 설명
```

## 🚀 실행 방법

### 1. 권장 실행 (모든 기능 포함)
```bash
bash start_ai_chat.sh
# 또는
./start_ai_chat.sh
```
- ✅ 자동 포트 포워딩
- ✅ 가상환경 자동 활성화
- ✅ 중복 실행 체크
- ✅ Windows 접속 지원

### 2. 간단 실행 (개발용)
```bash
source .venv/bin/activate  # 가상환경 활성화
./run_rag.sh
```

### 3. 직접 실행
```bash
source .venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src:$(pwd)/rag_system"
streamlit run src/web_interface.py --server.port 8501
```

## 📋 필수 파일 위치

| 파일명 | 위치 | 용도 |
|--------|------|------|
| web_interface.py | src/ | 메인 웹 UI |
| config.py | src/, 루트 | 설정 파일 |
| hybrid_chat_rag_v2.py | src/ | 통합 RAG |
| everything_like_search.py | src/ | 검색 모듈 |
| quick_fix_rag.py | src/ | 빠른 RAG |
| *.db | data/databases/ | 데이터베이스 |
| PDF 문서 | docs/ | 검색 대상 문서 |

## ⚠️ 주의사항

1. **경로 문제 발생 시**:
   - `config.py`는 루트와 src에 모두 있음 (호환성)
   - PYTHONPATH가 자동 설정됨

2. **모듈 import 오류 시**:
   - 필수 파일이 src에 있는지 확인
   - 가상환경이 활성화되었는지 확인

3. **백업 복원**:
   - `backup_20251023_210847/` 폴더에 원본 파일 보관
   - `archive/backups/`에 이전 버전들 보관

## 📊 정리 결과
- ✅ 16개 주요 폴더로 재구성
- ✅ 핵심 파일 5개 → src 폴더
- ✅ 백업 파일 3개 → archive/backups
- ✅ 문서 15개 → archive/documentation
- ✅ 데이터베이스 → data/databases

## 🔄 업데이트 이력
- 2025-10-23: 폴더 구조 대규모 정리
- 파일 경로 재구성 및 모듈 의존성 수정
- 실행 스크립트 업데이트