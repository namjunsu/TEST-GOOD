# 🐳 Docker로 AI-CHAT 옮기기 (진짜 쉬운 버전)

## Docker = "도시락 통" 🍱
- **일반 방법**: 재료 하나씩 옮기고 요리 다시 하기
- **Docker 방법**: 완성된 도시락 통째로 옮기기!

---

# 📦 현재 PC에서 (도시락 싸기)

## 1단계: Docker 설치
```bash
# WSL에서
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```
**WSL 재시작** (창 닫고 다시 열기)

## 2단계: Docker 이미지 만들기
```bash
cd /home/wnstn4647/AI-CHAT

# Dockerfile 수정 (새 파일 추가)
echo "COPY content_search.py metadata_db.py ./" >> Dockerfile
echo "COPY 초보자*.md MIGRATION_GUIDE.md ./" >> Dockerfile
echo "COPY *.sh ./" >> Dockerfile

# 이미지 빌드 (커피 타임 ☕ 15분)
docker build -t ai-chat:latest .
```

## 3단계: 이미지 저장
```bash
# 이미지를 파일로 (약 8GB)
docker save ai-chat:latest | gzip > ai-chat.tar.gz

# 데이터도 압축 (약 4.5GB)
tar -czf data.tar.gz models/ docs/

# USB로 복사
cp ai-chat.tar.gz data.tar.gz /mnt/c/Users/
```

---

# 💻 새 PC에서 (도시락 먹기)

## 1단계: Docker Desktop 설치
1. https://www.docker.com/products/docker-desktop/
2. 다운로드 → 설치 → 재시작
3. Docker Desktop 실행 (고래 아이콘 🐋)

## 2단계: 파일 준비
```powershell
# PowerShell에서
cd C:\
mkdir AI-CHAT
cd AI-CHAT

# USB에서 파일 2개 복사
# ai-chat.tar.gz (8GB)
# data.tar.gz (4.5GB)
```

## 3단계: Docker 이미지 로드
```powershell
# PowerShell에서
docker load < ai-chat.tar.gz
tar -xzf data.tar.gz
```

## 4단계: 실행!
```powershell
docker run -d `
  --name ai-chat `
  -p 8501:8501 `
  -v ${PWD}/models:/app/models `
  -v ${PWD}/docs:/app/docs `
  ai-chat:latest
```

## 5단계: 브라우저
**http://localhost:8501**

🎉 **끝!**

---

# 🆚 비교표

| 구분 | 일반 방법 | Docker 방법 |
|------|-----------|------------|
| Python 설치 | 필요 ✅ | 불필요 ❌ |
| CUDA 설치 | 필요 ✅ | 불필요 ❌ |
| 패키지 설치 | pip install (20개) | 불필요 ❌ |
| 환경 설정 | 수동 | 자동 |
| 에러 가능성 | 높음 | 낮음 |
| 소요 시간 | 30-40분 | 10분 |

---

# 🎯 한 줄 요약

## WSL → WSL (같은 환경)
```bash
# 그냥 압축이 빠름
tar -czf backup.tar.gz AI-CHAT/
# 새 PC에서
tar -xzf backup.tar.gz
```

## WSL → 다른 환경 (Windows/Mac)
```bash
# Docker가 최고!
docker build -t ai-chat .
docker save ai-chat > ai-chat.tar
# 새 PC에서
docker load < ai-chat.tar
docker run -p 8501:8501 ai-chat
```

---

# 💡 Docker 장점 정리

1. **설치 불필요**: Python? CUDA? Tesseract? Docker가 다 해결!
2. **100% 동일**: 에러 없이 똑같이 작동
3. **버전 관리**: 여러 버전 동시 보관 가능
4. **팀 공유**: 모두 같은 환경 사용
5. **롤백 가능**: 문제 생기면 이전 버전으로

---

# 🚨 자주 하는 실수

## ❌ 잘못된 방법
```bash
# 이미지만 복사 (데이터 없음)
docker save ai-chat > ai-chat.tar
# → 모델과 문서가 없어서 실행 안 됨!
```

## ✅ 올바른 방법
```bash
# 이미지 + 데이터 둘 다!
docker save ai-chat > ai-chat.tar
tar -czf data.tar.gz models/ docs/
# → 둘 다 있어야 작동!
```

---

# 📱 스마트폰에서도 사용!

Docker 실행 후:
1. PC IP 확인: `ipconfig`
2. 스마트폰 브라우저: `192.168.X.X:8501`
3. 같은 WiFi 연결 필수!

---

**Docker = 환경 통째로 도시락 싸기! 🍱**