# AI-CHAT RAG System Installation Guide
# 다른 PC에 설치할 때 필요한 완전 가이드

## 📋 시스템 요구사항

### 하드웨어
- **CPU**: 8코어 이상 권장
- **RAM**: 32GB 이상 (최소 16GB)
- **GPU**: NVIDIA GPU 16GB VRAM 이상 (RTX 4000 이상)
- **저장공간**: 50GB 이상 여유 공간

### 운영체제
- **Ubuntu 20.04/22.04** 또는 **WSL2 (Windows 11)**
- Python 3.8 이상

## 🔧 필수 시스템 패키지 설치

### 1. 기본 패키지 업데이트
```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Python 및 빌드 도구
```bash
sudo apt-get install -y python3 python3-pip python3-venv
sudo apt-get install -y build-essential cmake
sudo apt-get install -y git wget curl
```

### 3. OCR 관련 패키지 (Tesseract)
```bash
# Tesseract OCR 엔진 및 한국어 데이터
sudo apt-get install -y tesseract-ocr tesseract-ocr-kor
sudo apt-get install -y libtesseract-dev

# 확인
tesseract --version
tesseract --list-langs | grep kor
```

### 4. PDF 처리 패키지 (Poppler)
```bash
# PDF to Image 변환용
sudo apt-get install -y poppler-utils

# 확인
pdftoppm -v
```

### 5. 이미지 처리 라이브러리
```bash
sudo apt-get install -y libgl1-mesa-glx
sudo apt-get install -y libglib2.0-0
sudo apt-get install -y libsm6 libxext6 libxrender-dev libgomp1
```

## 🐍 Python 환경 설정

### 1. 가상환경 생성
```bash
cd /home/wnstn4647/AI-CHAT
python3 -m venv venv
source venv/bin/activate
```

### 2. pip 업그레이드
```bash
pip install --upgrade pip setuptools wheel
```

### 3. Python 패키지 설치
```bash
# 기본 패키지
pip install -r requirements_updated.txt

# OCR 관련 패키지
pip install pytesseract==0.3.10
pip install pdf2image==1.16.3
pip install Pillow==10.2.0

# 추가 필수 패키지
pip install streamlit==1.29.0
pip install llama-cpp-python==0.2.32
pip install sentence-transformers==2.2.2
pip install konlpy==0.6.0
pip install jpype1==1.4.1
pip install openpyxl==3.1.2
pip install pdfplumber==0.10.3
pip install python-dotenv==1.0.0
```

## 🤖 AI 모델 다운로드

### 1. Qwen2.5-7B 모델
```bash
# models 디렉토리 생성
mkdir -p models

# Qwen 모델 다운로드 (약 5GB x 2)
cd models
wget https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
wget https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf
cd ..
```

### 2. 한국어 임베딩 모델
```bash
# 첫 실행 시 자동 다운로드되지만 수동으로 하려면:
python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('jhgan/ko-sroberta-multitask')"
```

## ⚙️ 설정 파일

### 1. 환경 변수 파일 (.env)
```bash
cat > .env << 'EOF'
# 모델 경로
MODELS_DIR=/home/wnstn4647/AI-CHAT/models
DOCS_DIR=/home/wnstn4647/AI-CHAT/docs

# GPU 설정
N_GPU_LAYERS=-1
MAIN_GPU=0

# 디버그
DEBUG_MODE=false
LOG_LEVEL=INFO
EOF
```

### 2. Streamlit 설정
```bash
mkdir -p .streamlit
cat > .streamlit/config.toml << 'EOF'
[theme]
primaryColor = "#FF6B6B"
backgroundColor = "#1A1B26"
secondaryBackgroundColor = "#24283B"
textColor = "#C0CAF5"

[server]
port = 8501
maxUploadSize = 200
EOF
```

## 📁 디렉토리 구조 생성

```bash
# 필수 디렉토리 생성
mkdir -p docs
mkdir -p logs/queries
mkdir -p rag_system/cache
mkdir -p rag_system/db
mkdir -p rag_system/indexes
mkdir -p search_enhancement_data
mkdir -p archive/test_files
mkdir -p archive/old_docs
```

## 🔍 NVIDIA GPU 설정 (선택사항)

### 1. CUDA 설치 확인
```bash
nvidia-smi
nvcc --version
```

### 2. CUDA 없으면 설치
```bash
# CUDA 11.8 설치 (예시)
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-11-8
```

### 3. GPU 버전 llama-cpp 재설치
```bash
# GPU 지원 활성화하여 재설치
CMAKE_ARGS="-DLLAMA_CUBLAS=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
```

## 🚀 실행 및 테스트

### 1. 시스템 테스트
```bash
# 빠른 테스트
python quick_test.py

# OCR 테스트
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

### 2. 웹 인터페이스 실행
```bash
streamlit run web_interface.py
```

### 3. 자동 인덱싱 실행
```bash
# 별도 터미널에서
python auto_indexer.py
```

## 📝 문서 추가

1. **PDF 문서**: `docs/` 폴더에 복사
2. **Excel 장비 데이터**: `docs/equipment_data_*.xlsx` 형식으로 저장
3. **텍스트 파일**: `docs/` 폴더에 `.txt` 형식으로 저장

## 🔥 일반적인 문제 해결

### 1. Tesseract 언어 팩 누락
```bash
# 한국어 팩 재설치
sudo apt-get install --reinstall tesseract-ocr-kor
```

### 2. GPU 메모리 부족
```bash
# config.py에서 조정
N_GPU_LAYERS=20  # -1 대신 레이어 수 제한
N_BATCH=256      # 512에서 감소
```

### 3. ImportError 발생
```bash
# 패키지 재설치
pip install --force-reinstall -r requirements_updated.txt
```

### 4. 포트 충돌
```bash
# 다른 포트로 실행
streamlit run web_interface.py --server.port 8502
```

## 📊 성능 최적화 팁

1. **캐시 활용**: 응답 캐싱으로 30초→0.000초 속도 향상
2. **GPU 사용**: N_GPU_LAYERS=-1로 모든 레이어 GPU 처리
3. **컨텍스트 윈도우**: N_CTX=8192로 긴 문서 처리
4. **배치 크기**: N_BATCH=512로 처리량 증가

## 🔄 업데이트 방법

```bash
# 코드 업데이트
git pull origin main

# 패키지 업데이트
pip install --upgrade -r requirements_updated.txt

# 인덱스 재구축
python build_index.py
```

## 📌 중요 파일 체크리스트

### 필수 파일
- [ ] web_interface.py
- [ ] perfect_rag.py
- [ ] auto_indexer.py
- [ ] config.py
- [ ] requirements_updated.txt

### RAG 시스템 모듈
- [ ] rag_system/qwen_llm.py
- [ ] rag_system/hybrid_search.py
- [ ] rag_system/enhanced_ocr_processor.py
- [ ] rag_system/korean_vector_store.py
- [ ] rag_system/bm25_store.py

### 설정 파일
- [ ] .env
- [ ] .streamlit/config.toml

## 💾 백업 권장 사항

정기적으로 백업할 폴더:
- `docs/` - 모든 문서
- `rag_system/indexes/` - 인덱스 파일
- `rag_system/cache/` - OCR 캐시
- `logs/` - 로그 파일

## 🎯 설치 완료 확인

모든 설치가 완료되면 다음을 확인:
1. ✅ Streamlit 웹 인터페이스 정상 실행
2. ✅ PDF 문서 검색 기능 작동
3. ✅ 장비 자산 검색 기능 작동
4. ✅ OCR 기능 작동 (스캔 PDF 처리)
5. ✅ 응답 캐싱 작동 (2번째 질문부터 즉시 응답)
6. ✅ 자동 인덱싱 작동 (60초마다 docs 폴더 모니터링)

---
Last Updated: 2025-01-14 16:30
Author: AI-CHAT Development Team