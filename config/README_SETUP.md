# 🚀 AI-CHAT-V3 설치 및 실행 가이드

## 📋 시스템 요구사항

### 하드웨어
- **RAM**: 최소 16GB (권장 32GB)
- **저장공간**: 최소 50GB
- **GPU**: CUDA 지원 GPU 권장 (선택사항, CPU도 가능)

### 소프트웨어
- **OS**: Ubuntu 20.04+ / WSL2 (Windows)
- **Python**: 3.9 이상
- **CUDA**: 11.8+ (GPU 사용시)

## 🔧 설치 방법

### 1. 기본 패키지 설치

```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 패키지 설치
sudo apt install -y python3-pip python3-venv git wget curl
sudo apt install -y build-essential cmake
sudo apt install -y poppler-utils  # PDF 처리용

# Python 패키지 관리
pip install --upgrade pip
```

### 2. Python 가상환경 설정

```bash
# 프로젝트 디렉토리 이동
cd AI-CHAT-V3

# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate
```

### 3. Python 패키지 설치

```bash
# 핵심 패키지 설치
pip install streamlit==1.28.2
pip install pdfplumber==0.11.0
pip install llama-cpp-python==0.2.90
pip install sentence-transformers==2.2.2
pip install faiss-cpu==1.7.4
pip install rank_bm25==0.2.2
pip install konlpy==0.6.0
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 추가 패키지
pip install pandas numpy
pip install python-dotenv
pip install pathlib
```

### 4. 한국어 형태소 분석기 설치

```bash
# Mecab 설치 (선택사항, 더 정확한 한국어 처리)
sudo apt install -y mecab libmecab-dev mecab-ko-dic
pip install mecab-python3
```

### 5. 모델 파일 확인

```bash
# 모델 파일이 있는지 확인
ls -lh models/

# 필요한 파일:
# - qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf (약 4.4GB)
# - qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf (약 2.5GB)
```

⚠️ **모델 파일이 없는 경우**: 
- Hugging Face에서 다운로드하거나
- 기존 PC에서 복사해오세요

### 6. 인덱스 구축

```bash
# 처음 설치시 인덱스 생성 (약 5-10분 소요)
python build_index.py
```

## 🎯 실행 방법

### 웹 인터페이스 실행

```bash
# 기본 실행 (포트 8501)
streamlit run web_interface.py

# 특정 포트 지정
streamlit run web_interface.py --server.port 8502

# 네트워크 접속 허용
streamlit run web_interface.py --server.address 0.0.0.0
```

### 직접 테스트

```bash
# Python 인터프리터에서 직접 테스트
python3
>>> from perfect_rag import PerfectRAG
>>> rag = PerfectRAG(preload_llm=True)
>>> result = rag.answer("2025년 광화문 구매 내역 알려줘")
>>> print(result)
```

## 📁 디렉토리 구조

```
AI-CHAT-V3/
├── perfect_rag.py       # 메인 RAG 시스템
├── web_interface.py     # Streamlit 웹 UI
├── build_index.py       # 인덱싱 시스템
├── config.py           # 설정 파일
├── docs/               # PDF 문서 (25개)
├── models/             # LLM 모델 파일
├── rag_system/         # RAG 시스템 모듈
│   ├── qwen_llm.py    # LLM 인터페이스
│   ├── hybrid_search.py # 검색 엔진
│   └── ...
├── scripts/            # 실행 스크립트
└── archive/            # 이전 파일 (무시 가능)
```

## ⚙️ 설정 파일 (config.py)

필요시 수정:

```python
# 모델 경로
QWEN_MODEL_PATH = "./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"

# 문서 경로
DOCS_DIR = "./docs"

# 데이터베이스 경로
DB_DIR = "./rag_system/db"
```

## 🐛 문제 해결

### 1. CUDA/GPU 오류
```bash
# CPU 모드로 전환
export CUDA_VISIBLE_DEVICES=""
```

### 2. 메모리 부족
```bash
# config.py에서 수정
MAX_TOKENS = 2048  # 4096에서 줄이기
N_CTX = 2048      # 4096에서 줄이기
```

### 3. 포트 충돌
```bash
# 다른 포트 사용
streamlit run web_interface.py --server.port 8503
```

### 4. 인덱스 오류
```bash
# 인덱스 재구축
rm -rf rag_system/db/*
python build_index.py
```

## 🔒 보안 주의사항

- 민감한 문서가 있는 경우 접근 제한 설정
- 네트워크 노출시 방화벽 설정
- 정기적인 백업 권장

## 📞 지원

문제 발생시:
1. `archive/test_results/`에서 로그 확인
2. Python 환경 재설정
3. 인덱스 재구축

## ✅ 설치 확인

```bash
# 시스템 체크
python3 -c "
from perfect_rag import PerfectRAG
print('✅ Perfect RAG OK')
from web_interface import *
print('✅ Web Interface OK')
import config
print('✅ Config OK')
print('🎉 시스템 준비 완료!')
"
```

---
**작성일**: 2025-09-07  
**버전**: 3.0 (Perfect RAG)