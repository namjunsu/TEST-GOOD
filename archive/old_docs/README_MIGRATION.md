# AI-CHAT-V3 마이그레이션 패키지

이 패키지는 AI-CHAT-V3 시스템을 다른 PC로 완전히 이전하기 위한 모든 필수 파일들을 포함하고 있습니다.

## 📦 패키지 내용

### 폴더 구조
```
AI-CHAT-V3-MIGRATION/
├── 📁 core/                    # 핵심 Python 파일들 (6개)
│   ├── perfect_rag.py          # 메인 RAG 시스템 (145KB)
│   ├── web_interface.py        # Streamlit 웹 UI (54KB)
│   ├── build_index.py          # 인덱싱 시스템 (12KB)
│   ├── config.py               # 시스템 설정 (2KB)
│   ├── query_logger.py         # 쿼리 로깅 (11KB)
│   └── improve_answer_quality.py # 답변 품질 개선 (16KB)
│
├── 📁 rag_system/              # RAG 모듈들 (14개)
│   ├── hybrid_search.py        # 하이브리드 검색 엔진
│   ├── qwen_llm.py            # Qwen LLM 인터페이스
│   ├── korean_vector_store.py  # 한국어 벡터 스토어
│   └── ... 기타 필수 모듈들
│
├── 📁 docs/                   # 문서 파일들 (70MB)
│   ├── 48개 PDF 기안서/검토서 파일들
│   └── 채널A_방송장비_자산_전체_7904개_완전판.txt
│
├── 📁 config/                 # 설정 및 문서 파일들
│   ├── requirements.txt       # Python 패키지 목록
│   ├── requirements_updated.txt # 최신 패키지 목록
│   ├── .env                   # 환경 변수 템플릿
│   ├── CLAUDE.md              # 개발 가이드 (33KB)
│   ├── README.md              # 사용자 가이드 (8KB)
│   ├── README_SETUP.md        # 설치 가이드 (5KB)
│   └── *.png                  # 로고 이미지들
│
├── 📁 scripts/                # 자동 설치 스크립트들
│   ├── setup.sh               # Linux/WSL2 자동 설치
│   ├── setup.bat              # Windows 자동 설치
│   └── download_models.py     # 모델 자동 다운로드
│
└── 📄 문서들
    ├── MIGRATION_GUIDE.md     # 상세 마이그레이션 가이드
    └── README_MIGRATION.md    # 이 파일
```

### 총 용량: 91MB (모델 파일 제외)
- 📄 핵심 코드: 240KB
- 🔧 RAG 시스템: 350KB  
- 📚 문서 파일들: 70MB
- 🖼️ 이미지/기타: 20MB

## 🚀 빠른 설치 가이드

### 1단계: 패키지 준비
```bash
# 이 폴더를 새 PC로 복사
# 압축 파일이라면 압축 해제
tar -xzf AI-CHAT-V3-MIGRATION.tar.gz
cd AI-CHAT-V3-MIGRATION
```

### 2단계: 자동 설치 실행

**Linux/WSL2:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```cmd
# setup.bat을 우클릭 → "관리자 권한으로 실행"
```

### 3단계: 완료!
- 자동으로 `~/AI-CHAT-V3` (Linux) 또는 `%USERPROFILE%\AI-CHAT-V3` (Windows)에 설치됩니다
- 모델 파일 다운로드(4.4GB)는 자동으로 처리됩니다
- 설치 완료 후 `streamlit run web_interface.py`로 실행

## 📋 수동 설치 가이드

자동 설치가 실패한 경우 수동으로 설치할 수 있습니다:

### 1. 환경 준비
```bash
# Python 3.9+ 설치 확인
python3 --version

# 프로젝트 디렉토리 생성
mkdir ~/AI-CHAT-V3
cd ~/AI-CHAT-V3
```

### 2. 파일 복사
```bash
# 마이그레이션 패키지에서 파일들 복사
cp /path/to/AI-CHAT-V3-MIGRATION/core/* .
cp -r /path/to/AI-CHAT-V3-MIGRATION/rag_system .
cp -r /path/to/AI-CHAT-V3-MIGRATION/docs .
cp /path/to/AI-CHAT-V3-MIGRATION/config/* .
```

### 3. 가상환경 및 패키지 설치
```bash
python3 -m venv ai-chat-env
source ai-chat-env/bin/activate  # Linux
# ai-chat-env\Scripts\activate.bat  # Windows

pip install --upgrade pip
pip install -r requirements_updated.txt
```

### 4. 모델 다운로드
```bash
python3 download_models.py
```

### 5. 인덱싱 및 실행
```bash
python3 build_index.py
streamlit run web_interface.py
```

## ⚠️ 중요 사항

### 시스템 요구사항
- **Python**: 3.9 - 3.12 (3.12.3 권장)
- **메모리**: 최소 8GB, 권장 16GB
- **저장공간**: 10GB 이상 (모델 파일 4.4GB 포함)
- **운영체제**: Linux, Windows 10/11, macOS

### 포함되지 않은 파일들
- ❌ **모델 파일** (4.4GB) - 별도 다운로드 필요
- ❌ **생성된 인덱스 파일들** - 최초 실행시 자동 생성
- ❌ **로그 파일들** - 실행시 자동 생성
- ❌ **archive 폴더** - 불필요한 파일들 제외

### 보안 고려사항
- `.env` 파일의 API_KEY는 기본값 사용
- 민감한 정보가 포함된 로그는 제외됨
- PDF 문서들은 업무용 공개 문서만 포함

## 🔧 트러블슈팅

### 일반적인 문제들

1. **Python 버전 오류**
   - Python 3.9+ 설치 필요
   - `python3 --version` 확인

2. **패키지 설치 실패**
   - `pip install --upgrade pip setuptools wheel`
   - 시스템 의존성 설치: `sudo apt install build-essential python3-dev`

3. **모델 다운로드 실패**
   - 인터넷 연결 확인
   - `python3 download_models.py --method wget` 시도
   - 수동 다운로드: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF

4. **메모리 부족**
   - 스왑 파일 생성
   - Chrome/브라우저 종료
   - 청크 크기 조정 (config.py)

5. **포트 충돌**
   - `streamlit run web_interface.py --server.port 8502`
   - 방화벽 설정 확인

### 로그 확인
```bash
# 설치 후 로그 위치
tail -f ~/AI-CHAT-V3/rag_system/logs/rag_system.log

# 오류 검색
grep "ERROR" ~/AI-CHAT-V3/rag_system/logs/*.log
```

## 📞 지원

### 추가 도움말
- 📖 **상세 가이드**: `MIGRATION_GUIDE.md` 참조
- 🔧 **개발 문서**: `CLAUDE.md` 참조  
- 👥 **사용법**: `README.md` 참조

### 검증된 환경
- ✅ **Ubuntu 22.04 + Python 3.12.3**
- ✅ **Windows 11 + WSL2 + Python 3.12**
- ✅ **macOS Monterey + Python 3.11** (실험적)

### 성능 참고
- **인덱싱 시간**: 2-5분 (SSD 기준)
- **메모리 사용량**: 2-4GB (실행시)
- **응답 시간**: 1-3초 (일반 질문)

---

**✅ 마이그레이션 패키지 버전**: 2025-09-10  
**🎯 원본 시스템 버전**: AI-CHAT-V3 Production  
**📊 테스트 완료**: Linux + Windows 환경