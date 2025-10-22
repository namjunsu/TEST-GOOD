# 🐳 Docker로 AI-CHAT 사용하기

> Docker를 사용하면 **어떤 PC에서도 동일하게** 실행할 수 있습니다!

---

## 🎯 Docker를 사용하는 이유

### ✅ 장점
- **환경 통일**: 모든 PC에서 동일한 Python 버전, 라이브러리 버전 사용
- **간편한 설치**: `docker-compose up` 한 줄로 실행
- **이식성**: 집 PC → 회사 PC 옮길 때 문제 없음
- **격리성**: 기존 Python 환경과 충돌 없음

### ⚠️ 주의사항
- Docker Desktop (Windows) 또는 Docker Engine (Linux) 필요
- 첫 빌드 시간이 좀 걸림 (5-10분, 이후는 빠름)
- 대용량 모델 파일(.gguf)은 별도 관리 필요

---

## 📦 설치 방법

### 1. Docker 설치

**Windows (WSL2)**:
```bash
# Docker Desktop 다운로드 및 설치
# https://www.docker.com/products/docker-desktop

# WSL2에서 확인
docker --version
docker-compose --version
```

**Ubuntu/Linux**:
```bash
# Docker 설치
sudo apt update
sudo apt install docker.io docker-compose

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 재로그인 후 확인
docker --version
```

### 2. 필수 파일 확인

```bash
cd /home/wnstn4647/AI-CHAT

# 다음 파일들이 있는지 확인
ls -lh
# - Dockerfile
# - docker-compose.yml
# - .env
# - requirements.txt
# - qwen2.5-7b-instruct-q4_k_m-00001-of-00002-001.gguf (LLM 모델)
# - docs/ (PDF 문서들)
```

---

## 🚀 실행 방법

### 빠른 시작 (한 줄)

```bash
docker-compose up -d
```

이게 끝입니다! 브라우저에서 `http://localhost:8501` 접속

### 상세 명령어

```bash
# 1. 이미지 빌드 (처음 한 번만)
docker-compose build

# 2. 컨테이너 시작 (백그라운드)
docker-compose up -d

# 3. 로그 확인
docker-compose logs -f

# 4. 중지
docker-compose down

# 5. 재시작
docker-compose restart
```

---

## 🖥️ 다른 PC로 옮기기

### 방법 1: Git + Docker (추천)

**현재 PC**:
```bash
# Git 저장소에 푸시
git add .
git commit -m "Docker 설정 추가"
git push
```

**새 PC**:
```bash
# 코드 다운로드
git clone <저장소 URL>
cd AI-CHAT

# 필수 파일 복사 (수동)
# - .env 파일
# - qwen2.5-7b-instruct-q4_k_m-00001-of-00002-001.gguf
# - docs/ 폴더

# 실행
docker-compose up -d
```

### 방법 2: 전체 백업 + Docker

**현재 PC**:
```bash
# 백업 생성 (기존 방법)
./QUICK_MIGRATION.sh

# USB에 복사
cp AI-CHAT_backup_*.tar.gz /mnt/d/
```

**새 PC**:
```bash
# 백업 복원
tar -xzf AI-CHAT_backup_*.tar.gz
cd AI-CHAT

# Docker로 실행
docker-compose up -d
```

### 방법 3: Docker Hub 사용 (고급)

**현재 PC**:
```bash
# 이미지 빌드
docker-compose build

# Docker Hub에 로그인
docker login

# 이미지 태그
docker tag ai-chat-app:latest <username>/ai-chat:latest

# 업로드
docker push <username>/ai-chat:latest
```

**새 PC**:
```bash
# docker-compose.yml 수정
# image: <username>/ai-chat:latest

# 다운로드 및 실행
docker-compose up -d
```

---

## 🔧 문제 해결

### 컨테이너가 시작되지 않을 때

```bash
# 로그 확인
docker-compose logs

# 컨테이너 상태 확인
docker ps -a

# 강제 재빌드
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 모델 파일(.gguf)이 없을 때

```bash
# 에러: cannot find model file
# 해결: 모델 파일을 AI-CHAT 폴더에 복사
cp /path/to/qwen2.5-7b-instruct-q4_k_m-00001-of-00002-001.gguf .
```

### 포트가 이미 사용 중일 때

```bash
# docker-compose.yml 수정
ports:
  - "8502:8501"  # 8502로 변경

# 재시작
docker-compose up -d

# 브라우저: http://localhost:8502
```

### 메모리 부족

```bash
# docker-compose.yml의 메모리 제한 조정
deploy:
  resources:
    limits:
      memory: 4G  # 8G → 4G로 줄이기
```

---

## 📊 상태 확인

```bash
# 실행 중인 컨테이너 확인
docker ps

# 리소스 사용량 확인
docker stats ai-chat-app

# 컨테이너 안으로 들어가기
docker exec -it ai-chat-app bash
```

---

## 🧹 정리

```bash
# 컨테이너 중지 및 삭제
docker-compose down

# 이미지도 함께 삭제
docker-compose down --rmi all

# 볼륨까지 삭제 (주의! 데이터 손실)
docker-compose down -v

# 사용하지 않는 이미지 정리
docker system prune -a
```

---

## 💡 팁

### 1. 개발 모드로 실행
```bash
# docker-compose.yml에 추가
volumes:
  - .:/app  # 코드 실시간 반영
```

### 2. 빠른 재시작
```bash
# 코드 수정 후
docker-compose restart
```

### 3. 백그라운드 vs 포그라운드
```bash
# 백그라운드 (터미널 닫아도 실행)
docker-compose up -d

# 포그라운드 (로그 바로 보기)
docker-compose up
```

---

## 📋 체크리스트

실행 전 확인:
- [ ] Docker 설치됨
- [ ] .env 파일 있음
- [ ] 모델 파일(.gguf) 있음
- [ ] docs/ 폴더 있음
- [ ] docker-compose.yml 있음

실행 후 확인:
- [ ] `docker ps`로 컨테이너 실행 확인
- [ ] http://localhost:8501 접속됨
- [ ] 검색 기능 동작함
- [ ] AI 답변 생성됨

---

## 🆚 Docker vs 일반 실행 비교

| 항목 | 일반 실행 | Docker 실행 |
|------|----------|-------------|
| 설치 | Python, pip, 패키지 수동 설치 | Docker만 설치 |
| 환경 | PC마다 다를 수 있음 | 항상 동일 |
| 속도 | 약간 빠름 | 약간 느림 (무시 가능) |
| 이식성 | 낮음 | 높음 |
| 격리성 | 없음 | 완벽한 격리 |

---

## 📞 도움말

- **Docker 기본**: [Docker 공식 문서](https://docs.docker.com/)
- **프로젝트 문제**: [문제해결.md](문제해결.md)
- **일반 실행**: [START_HERE.md](START_HERE.md)

---

**버전**: 1.0
**작성일**: 2025-10-21
**Docker 버전**: 20.10+, Docker Compose 1.29+
