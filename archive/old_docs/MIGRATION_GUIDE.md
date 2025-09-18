# AI-CHAT-V3 시스템 마이그레이션 가이드

## 📋 시스템 개요
AI-CHAT-V3는 한국어 방송장비 문서 분석을 위한 RAG(Retrieval-Augmented Generation) 시스템입니다.

## 🔧 시스템 요구사항

### 하드웨어 요구사항
- **CPU**: 4코어 이상 (Intel i5 또는 AMD Ryzen 5 이상 권장)
- **RAM**: 최소 8GB, 권장 16GB
- **저장공간**: 최소 10GB (모델 파일 5GB + 문서 100MB + 시스템 파일)
- **네트워크**: 모델 다운로드를 위한 인터넷 연결

### 소프트웨어 요구사항
- **운영체제**: 
  - Linux Ubuntu 18.04+ (권장)
  - Windows 10/11 + WSL2
  - macOS 10.15+ (실험적 지원)
- **Python**: 3.9 - 3.12 (Python 3.12.3 권장)
- **Git**: 최신 버전

## 🚀 설치 방법

### 1단계: 기본 환경 준비

#### Linux/WSL2:
```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# Python 및 필수 도구 설치
sudo apt install -y python3 python3-pip python3-venv git wget curl

# Python 버전 확인
python3 --version  # 3.9+ 이어야 함
```

#### Windows:
```cmd
# Python 3.9+ 설치 (python.org에서 다운로드)
# Git 설치 (git-scm.com에서 다운로드)
# PowerShell을 관리자 권한으로 실행
```

### 2단계: 프로젝트 설정

```bash
# 작업 디렉토리 생성
mkdir -p ~/AI-CHAT-V3
cd ~/AI-CHAT-V3

# 마이그레이션 파일 압축 해제 (전달받은 파일)
# AI-CHAT-V3-MIGRATION.tar.gz를 현재 디렉토리에 복사 후:
tar -xzf AI-CHAT-V3-MIGRATION.tar.gz

# 파일 구조 복원
cp core/* .
cp -r rag_system .
cp -r docs .
cp config/* .

# 가상환경 생성
python3 -m venv ai-chat-env
source ai-chat-env/bin/activate  # Linux/WSL2
# ai-chat-env\Scripts\activate.bat  # Windows

# 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

### 3단계: 모델 파일 다운로드

모델 파일은 약 4.4GB이므로 별도로 다운로드해야 합니다:

```bash
# models 디렉토리 생성
mkdir -p models

# Qwen2.5-7B 모델 다운로드 (Hugging Face에서)
wget -O models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"

wget -O models/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf"
```

대안: huggingface-hub를 사용한 다운로드:
```bash
pip install huggingface-hub
python3 -c "
from huggingface_hub import hf_hub_download
import os
os.makedirs('models', exist_ok=True)
hf_hub_download(repo_id='Qwen/Qwen2.5-7B-Instruct-GGUF', filename='qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf', local_dir='models')
hf_hub_download(repo_id='Qwen/Qwen2.5-7B-Instruct-GGUF', filename='qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf', local_dir='models')
"
```

### 4단계: 환경 설정

```bash
# .env 파일 수정
cat > .env << 'EOF'
MODEL_PATH=./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
DB_DIR=./rag_system/db
LOG_DIR=./rag_system/logs
API_KEY=broadcast-tech-rag-2025
STREAMLIT_SERVER_PORT=8501
EOF
```

### 5단계: 인덱스 구축

```bash
# 문서 인덱싱 (최초 1회 실행)
python3 build_index.py
```

예상 출력:
```
📄 문서 처리 중... (48개 PDF 파일)
🔍 벡터 인덱스 생성 중...
📊 BM25 인덱스 생성 중...
✅ 인덱싱 완료!
```

### 6단계: 시스템 테스트

```bash
# 기본 기능 테스트
python3 -c "
from perfect_rag import PerfectRAG
rag = PerfectRAG()
result = rag.query('시스템 테스트')
print('✅ 시스템 정상 작동')
"

# 웹 인터페이스 실행
streamlit run web_interface.py
```

브라우저에서 http://localhost:8501 접속하여 확인

## 📁 최종 디렉토리 구조

```
~/AI-CHAT-V3/
├── 📄 핵심 파일
│   ├── perfect_rag.py          # 메인 RAG 시스템
│   ├── web_interface.py        # Streamlit 웹 UI
│   ├── build_index.py          # 인덱싱 시스템
│   ├── config.py               # 시스템 설정
│   └── query_logger.py         # 쿼리 로깅
│
├── 📂 rag_system/              # RAG 모듈들
│   ├── hybrid_search.py        # 하이브리드 검색
│   ├── qwen_llm.py            # LLM 인터페이스
│   ├── korean_vector_store.py  # 벡터 스토어
│   └── ...기타 모듈들
│
├── 📚 docs/                    # 48개 PDF 문서들
│   ├── *.pdf                  # 방송장비 기안서/검토서
│   └── 채널A_방송장비_자산_전체_7904개_완전판.txt
│
├── 🤖 models/                  # 4.4GB 모델 파일들
│   ├── qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
│   └── qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf
│
├── ⚙️ 설정 파일들
│   ├── requirements.txt        # Python 패키지 목록
│   ├── .env                   # 환경 변수
│   ├── CLAUDE.md              # 개발 가이드
│   └── README.md              # 사용자 가이드
│
└── 🗂️ 생성되는 파일들
    ├── rag_system/db/         # 벡터/BM25 인덱스
    └── rag_system/logs/       # 로그 파일들
```

## 🔧 트러블슈팅

### 문제 1: 패키지 설치 오류
```bash
# 해결방법 1: pip 업그레이드
pip install --upgrade pip setuptools wheel

# 해결방법 2: 시스템 패키지 설치 (Linux)
sudo apt install -y python3-dev build-essential

# 해결방법 3: conda 사용
conda install -c conda-forge faiss-cpu sentence-transformers
```

### 문제 2: 모델 다운로드 실패
```bash
# 직접 다운로드 링크 사용
curl -L -o models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
```

### 문제 3: 메모리 부족
```bash
# swap 파일 생성 (Linux)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 문제 4: Streamlit 실행 오류
```bash
# 포트 변경
streamlit run web_interface.py --server.port 8502

# 방화벽 확인
sudo ufw allow 8501
```

### 문제 5: 인덱싱 오류
```bash
# 인덱스 재구축
rm -rf rag_system/db/*
python3 build_index.py
```

## 📞 지원 및 문의

### 로그 확인
```bash
# 최신 로그 확인
tail -f rag_system/logs/rag_system.log

# 오류 로그 검색
grep "ERROR" rag_system/logs/*.log
```

### 시스템 상태 확인
```bash
# 메모리 사용량
free -h

# 디스크 공간
df -h

# Python 패키지 상태
pip list | grep -E "(streamlit|sentence|faiss)"
```

### 성능 최적화
- CPU 코어 수에 따른 스레드 조정
- 메모리가 부족한 경우 문서 청크 크기 조정
- SSD 사용 권장 (인덱싱 속도 향상)

## 🎯 사용법

1. **웹 인터페이스**: `streamlit run web_interface.py`
2. **직접 테스트**: `python3 perfect_rag.py`
3. **시스템 재시작**: 웹 UI의 "🔄 시스템 재시작" 버튼

### 최적 질문 예시:
- "뷰파인더 케이블 구매 기안자는?"
- "2024년 방송소모품 관련 문서 찾아줘"
- "드론장비 수리 내용 요약해줘"

**설치 완료 후 브라우저에서 http://localhost:8501 접속하여 시스템을 확인하세요!**

---
📅 **최종 업데이트**: 2025-09-10  
🔧 **시스템 버전**: AI-CHAT-V3 Production  
📊 **테스트 환경**: Ubuntu 22.04 + Python 3.12.3