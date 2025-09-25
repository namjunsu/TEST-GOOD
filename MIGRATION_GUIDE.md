# 🚀 AI-CHAT 프로젝트 이전 가이드

## 📋 체크리스트

### 필수 파일들:
- [ ] 소스 코드 (Git으로 관리)
- [ ] 모델 파일: `models/` (약 4.5GB)
- [ ] PDF 문서: `docs/` (480개 파일)
- [ ] 캐시/인덱스: `cache/`, `indexes/`, `rag_system/db/`

## 🔄 이전 방법

### 방법 1: Git + 대용량 파일 직접 복사 (권장)

#### 현재 PC (WSL)에서:
```bash
# 1. Git 원격 저장소 추가 (GitHub 등)
git remote add origin https://github.com/your-username/ai-chat.git
git push -u origin master

# 2. 대용량 파일 압축
# 모델 파일 압축 (약 4.5GB)
tar -czf models.tar.gz models/

# PDF 문서 압축 (선택사항)
tar -czf docs.tar.gz docs/

# 3. 파일 목록 생성
ls -la models/ > file_list.txt
find docs -name "*.pdf" | wc -l  # PDF 개수 확인
```

#### 새 PC에서:
```bash
# 1. Git 클론
git clone https://github.com/your-username/ai-chat.git
cd ai-chat

# 2. Python 환경 설정
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows

# 3. 패키지 설치
pip install -r requirements_updated.txt

# 4. 대용량 파일 복사
# USB나 네트워크로 models.tar.gz, docs.tar.gz 전송 후
tar -xzf models.tar.gz
tar -xzf docs.tar.gz

# 5. 디렉토리 생성
mkdir -p cache indexes logs rag_system/db

# 6. 실행
streamlit run web_interface.py
```

### 방법 2: Docker 사용 (깔끔한 이전)

#### 현재 PC에서:
```bash
# Docker 이미지 빌드
docker build -t ai-chat:latest .

# 이미지 저장
docker save ai-chat:latest | gzip > ai-chat.tar.gz

# 데이터 볼륨 백업
tar -czf data-backup.tar.gz models/ docs/ cache/ indexes/
```

#### 새 PC에서:
```bash
# Docker 이미지 로드
docker load < ai-chat.tar.gz

# 데이터 복원
tar -xzf data-backup.tar.gz

# Docker Compose로 실행
docker-compose up -d
```

### 방법 3: 전체 WSL 백업 (WSL2 환경 그대로 이전)

#### 현재 PC에서:
```powershell
# PowerShell (관리자 권한)
# WSL 종료
wsl --shutdown

# WSL 배포판 목록 확인
wsl -l -v

# 백업 (약 20-30GB)
wsl --export Ubuntu C:\backup\ubuntu-ai-chat.tar
```

#### 새 PC에서:
```powershell
# WSL2 설치 확인
wsl --install

# 백업 가져오기
wsl --import AI-CHAT C:\WSL\AI-CHAT C:\backup\ubuntu-ai-chat.tar

# 실행
wsl -d AI-CHAT
```

## 📦 필수 파일 크기

```
models/
├── qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf (2.3GB)
└── qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf (2.2GB)
총: 약 4.5GB

docs/
├── year_2014/ ~ year_2025/  (480개 PDF)
총: 약 1-2GB

전체 프로젝트: 약 6-7GB
```

## ⚙️ 환경 설정

### 새 PC 최소 사양:
- **RAM**: 16GB 이상
- **GPU**: NVIDIA GPU + CUDA 12.1 (선택사항, 없으면 CPU 모드)
- **디스크**: 20GB 이상 여유 공간

### CUDA 설정 (GPU 사용 시):
```bash
# CUDA 12.1 설치
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-12-1

# 환경변수 설정
echo 'export PATH=/usr/local/cuda-12.1/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### CPU 모드로 실행 (GPU 없을 때):
```python
# config.py 수정
N_GPU_LAYERS = 0  # GPU 사용 안 함
N_THREADS = 8     # CPU 코어에 맞게 조정
```

## 🔍 이전 후 확인사항

```bash
# 1. 파일 확인
ls -la models/
find docs -name "*.pdf" | wc -l  # 480개 확인

# 2. Python 패키지 확인
pip list | grep -E "streamlit|llama-cpp-python|pdfplumber"

# 3. 테스트 실행
python3 quick_test.py

# 4. 웹 인터페이스 실행
streamlit run web_interface.py
```

## 💡 문제 해결

### 1. 모델 로딩 실패
```bash
# 모델 파일 체크섬 확인
md5sum models/*.gguf

# 권한 확인
chmod 644 models/*.gguf
```

### 2. PDF 파일 없음
```bash
# docs 폴더 구조 확인
tree docs -d

# PDF 개수 확인
find docs -name "*.pdf" | wc -l
```

### 3. 패키지 설치 오류
```bash
# pip 업그레이드
pip install --upgrade pip

# 개별 설치
pip install streamlit==1.31.0
pip install llama-cpp-python==0.2.28
```

## 📝 빠른 시작 (새 PC)

```bash
# 1. 프로젝트 클론
git clone [your-repo-url] ai-chat
cd ai-chat

# 2. 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 3. 패키지 설치
pip install -r requirements_updated.txt

# 4. 모델/문서 복사 (USB 등으로)
# models/ 폴더와 docs/ 폴더 복사

# 5. 실행
streamlit run web_interface.py
```

## 🆘 도움말

- 모델 파일이 너무 크면 Google Drive나 OneDrive 사용
- Git LFS 사용 시 `.gitattributes` 파일 확인
- WSL2가 없으면 일반 Ubuntu나 Docker Desktop 사용 가능

---
작성일: 2025-09-25