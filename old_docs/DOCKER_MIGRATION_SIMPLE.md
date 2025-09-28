# 🐳 Docker로 AI-CHAT 프로젝트 쉽게 옮기기

## Docker가 뭐야?
**Docker = "이사할 때 짐을 박스에 담는 것"**
- 우리 앱(AI-CHAT)과 필요한 모든 것(Python, 라이브러리 등)을 하나의 박스(컨테이너)에 담아요
- 이 박스를 새 PC로 옮기면 똑같이 작동해요!

## 🎯 왜 Docker가 좋아?
1. **설치 불필요**: 새 PC에 Python, CUDA, 패키지 등 설치 안 해도 됨
2. **100% 동일**: 현재 환경 그대로 새 PC에서 실행
3. **쉬움**: 명령어 몇 개로 끝!

---

# 📋 Docker 이전 단계별 가이드

## 🔴 현재 PC (WSL)에서 할 일

### 1단계: Docker 설치 확인
```bash
# Docker 있는지 확인
docker --version

# 없으면 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### 2단계: Docker 이미지 만들기
```bash
# AI-CHAT 폴더로 이동
cd /home/wnstn4647/AI-CHAT

# Docker 이미지 빌드 (10-15분 소요)
docker build -t ai-chat:latest .
```

### 3단계: 이미지를 파일로 저장
```bash
# Docker 이미지를 파일로 (약 8GB)
docker save ai-chat:latest | gzip > ai-chat-docker.tar.gz

# 크기 확인
ls -lh ai-chat-docker.tar.gz
```

### 4단계: 데이터 압축
```bash
# 모델과 문서 압축 (약 4.5GB)
tar -czf ai-chat-data.tar.gz models/ docs/
```

### 5단계: USB나 클라우드에 복사
```bash
# 두 파일을 USB나 Google Drive에 복사
# 1. ai-chat-docker.tar.gz (Docker 이미지, 약 8GB)
# 2. ai-chat-data.tar.gz (모델+문서, 약 4.5GB)
```

---

## 🔵 새 PC에서 할 일

### 1단계: Docker Desktop 설치
1. **Windows**: https://www.docker.com/products/docker-desktop/
2. 다운로드 → 설치 → 재부팅
3. Docker Desktop 실행

### 2단계: 파일 가져오기
```bash
# USB나 클라우드에서 파일 2개 복사
# C:\AI-CHAT\ 폴더 만들고 거기에 복사
```

### 3단계: Docker 이미지 로드
```bash
# PowerShell이나 CMD 열기
cd C:\AI-CHAT

# Docker 이미지 로드 (5분 소요)
docker load < ai-chat-docker.tar.gz
```

### 4단계: 데이터 압축 해제
```bash
# 데이터 폴더 압축 해제
tar -xzf ai-chat-data.tar.gz
```

### 5단계: 실행!
```bash
# Docker 컨테이너 실행
docker run -d \
  --name ai-chat \
  -p 8501:8501 \
  -v ${PWD}/models:/app/models \
  -v ${PWD}/docs:/app/docs \
  ai-chat:latest

# 브라우저에서 열기
# http://localhost:8501
```

---

# 🎉 더 쉬운 방법: docker-compose 사용

## docker-compose.yml 파일 만들기
```yaml
version: '3.8'
services:
  ai-chat:
    image: ai-chat:latest
    ports:
      - "8501:8501"
    volumes:
      - ./models:/app/models
      - ./docs:/app/docs
      - ./cache:/app/cache
      - ./indexes:/app/indexes
    environment:
      - CUDA_VISIBLE_DEVICES=0
    restart: unless-stopped
```

## 실행
```bash
# 시작
docker-compose up -d

# 중지
docker-compose down

# 로그 보기
docker-compose logs -f
```

---

# 🚨 자주 묻는 질문

## Q1: GPU 없는 PC에서도 되나요?
**A**: 됩니다! 좀 느리지만 CPU로 실행됩니다.
```bash
# GPU 없을 때 실행
docker run -d \
  --name ai-chat \
  -p 8501:8501 \
  -v ${PWD}/models:/app/models \
  -v ${PWD}/docs:/app/docs \
  -e CUDA_VISIBLE_DEVICES="" \
  ai-chat:latest
```

## Q2: 파일이 너무 커요!
**A**: 두 가지 방법:
1. **Google Drive 사용**:
   - ai-chat-docker.tar.gz 업로드
   - ai-chat-data.tar.gz 업로드
   - 새 PC에서 다운로드

2. **분할 압축**:
```bash
# 2GB씩 분할
split -b 2G ai-chat-docker.tar.gz ai-chat-docker.tar.gz.part
# 합치기
cat ai-chat-docker.tar.gz.part* > ai-chat-docker.tar.gz
```

## Q3: Docker 없이는 안되나요?
**A**: 되지만 복잡합니다:
- Python 3.10 설치
- CUDA 12.1 설치 (GPU 있으면)
- 모든 패키지 설치
- 환경변수 설정
- 오류 해결...

Docker는 이 모든 걸 자동으로 해줍니다!

---

# 🎯 한 줄 요약

## 현재 PC:
```bash
docker build -t ai-chat:latest .
docker save ai-chat:latest | gzip > ai-chat-docker.tar.gz
tar -czf ai-chat-data.tar.gz models/ docs/
# USB에 복사
```

## 새 PC:
```bash
# Docker Desktop 설치 후
docker load < ai-chat-docker.tar.gz
tar -xzf ai-chat-data.tar.gz
docker run -d -p 8501:8501 -v ${PWD}/models:/app/models -v ${PWD}/docs:/app/docs ai-chat:latest
# http://localhost:8501 접속
```

---

# 💡 Pro Tips

1. **Docker Desktop 메모리 설정**:
   - 설정 → Resources → Memory: 8GB 이상

2. **GPU 사용 (NVIDIA)**:
   - Docker Desktop → Settings → Resources → GPU 활성화

3. **자동 시작**:
   - `--restart always` 옵션 추가하면 PC 재시작해도 자동 실행

4. **백업**:
   - Docker 이미지는 한 번만 만들면 됨
   - 데이터(models/, docs/)만 주기적으로 백업

---

끝! 🎉 이제 어디서든 AI-CHAT을 실행할 수 있어요!