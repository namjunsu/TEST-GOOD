# 📁 AI-CHAT 폴더 구조 가이드

## 🚀 **핵심 실행 파일들** (메인 기능)
```
📄 web_interface.py       - Streamlit 웹 UI (메인 인터페이스)
📄 perfect_rag.py         - RAG 엔진 (문서 검색 및 질의응답)
📄 everything_like_search.py - 고속 검색 엔진
📄 config.py              - 시스템 설정
🚀 start_ai_chat.sh       - 시스템 시작 스크립트
📋 requirements.txt       - Python 의존성
```

## 📊 **데이터 및 캐시**
```
📚 docs/                  - PDF 문서들 (480개, 연도별/카테고리별 분류)
🗄️ everything_index.db    - 문서 인덱스 데이터베이스
🗄️ pdf_cache.db          - PDF 캐시 데이터베이스
🗄️ metadata.db           - 메타데이터 저장소
📁 cache/                 - 캐시 데이터
📁 ocr_cache/             - OCR 캐시
📁 indexes/               - 검색 인덱스
```

## 🧩 **시스템 모듈**
```
📁 modules/               - 핵심 RAG 시스템 모듈들
📁 rag_system/            - RAG 시스템 컴포넌트
📁 config/                - 설정 파일들
```

## 🔧 **개발 환경**
```
📁 venv/                  - Python 가상환경
📁 models/                - AI 모델 파일들 (5.2GB)
📁 logs/                  - 시스템 로그
📄 .env                   - 환경 변수
📄 README.md              - 프로젝트 설명
```

## 🗂️ **정리된 미사용 파일들** (unused_files/)
```
📁 unused_files/
├── 🐳 docker/            - Docker 관련 파일들 (Dockerfile, docker-compose.yml)
├── 📊 benchmarks/        - 성능 벤치마크 파일들
├── ⚙️ development/       - 개발 스크립트들
├── 🔧 future_configs/    - 미래 배포용 설정 (.env.production)
├── 📁 archive_folders/   - 아카이브 폴더들
├── 📝 logs/              - 오래된 로그 파일들
├── 📋 old_dependencies/  - 오래된 의존성 파일들
├── 🛠️ utils/             - 유틸리티 스크립트들
├── 🧪 tests/             - 테스트 파일들
└── 📁 old_utils/         - 오래된 유틸리티 폴더
```

## 🎯 **처음 사용자를 위한 가이드**

### 시스템 실행:
```bash
./start_ai_chat.sh
```

### 웹 접속:
```
http://localhost:8501
```

### 주요 파일만 신경쓰면 됩니다:
- `web_interface.py` - 웹 UI
- `perfect_rag.py` - 검색 엔진
- `docs/` - 문서들
- `venv/` - 실행 환경

**나머지는 모두 보조 파일들이니 무시하셔도 됩니다!**