# 📊 AI-CHAT 모니터링 가이드

## 🚀 Docker 실행 & 모니터링

### 1. 실행하기
```bash
# 포그라운드 실행 (로그 바로 보기)
docker compose up --build

# 백그라운드 실행
docker compose up -d --build
```

### 2. 실시간 모니터링 (새 터미널 열어서)

#### 📝 로그 모니터링
```bash
# 모든 서비스 로그 보기
docker compose logs -f

# 특정 서비스만 보기
docker compose logs -f rag-system

# 최근 100줄만 보고 계속 모니터링
docker compose logs -f --tail=100
```

#### 📈 리소스 모니터링
```bash
# CPU/메모리 실시간 모니터링 (1초마다 갱신)
docker stats

# 특정 컨테이너만 모니터링
docker stats ai-chat-rag

# 깔끔한 포맷으로 보기
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

#### 🔍 컨테이너 상태 확인
```bash
# 실행 중인 컨테이너 확인
docker ps

# 모든 컨테이너 (중지된 것 포함)
docker ps -a

# Docker Compose 서비스 상태
docker compose ps
```

---

## 📱 웹 브라우저에서 모니터링

### 1. Streamlit 웹 UI (http://localhost:8501)
- **왼쪽 사이드바**에서 시스템 상태 확인
  - ✅ 문서 로딩 상태
  - 📊 캐시 통계
  - 🔄 응답 시간

### 2. Grafana 대시보드 (http://localhost:3000)
```
기본 로그인:
- Username: admin
- Password: admin
```
- **시스템 메트릭** 실시간 확인
- **응답 시간 그래프**
- **에러율 모니터링**

---

## 🖥️ 터미널 모니터링 명령어 모음

### 기본 모니터링
```bash
# 컨테이너 로그 실시간
docker logs -f ai-chat-rag

# 로그에서 에러만 찾기
docker logs ai-chat-rag 2>&1 | grep ERROR

# 로그에서 특정 키워드 찾기
docker logs ai-chat-rag 2>&1 | grep "문서 로딩"
```

### 고급 모니터링
```bash
# 컨테이너 내부 접속해서 확인
docker exec -it ai-chat-rag /bin/bash

# 내부에서 Python 프로세스 확인
docker exec ai-chat-rag ps aux | grep python

# 내부 로그 파일 확인
docker exec ai-chat-rag tail -f /app/logs/system.log
```

### 시스템 리소스 모니터링
```bash
# Docker 전체 디스크 사용량
docker system df

# 컨테이너별 상세 정보
docker inspect ai-chat-rag | grep -A 5 "Memory"

# 네트워크 상태
docker network ls
docker port ai-chat-rag
```

---

## 🎯 모니터링 체크리스트

### ✅ 정상 작동 확인 사항
```
□ docker ps에서 ai-chat-rag 상태가 "Up"
□ http://localhost:8501 접속 가능
□ CPU 사용률 < 80%
□ 메모리 사용량 < 12GB
□ 로그에 ERROR 없음
□ 응답 시간 < 5초
```

### ⚠️ 문제 징후
```
❌ Container 상태가 "Exited"
❌ 메모리 사용량 > 14GB
❌ CPU 지속적으로 100%
❌ 로그에 반복적인 ERROR
❌ 웹 페이지 접속 불가
```

---

## 🔧 문제 해결

### 컨테이너가 계속 재시작되는 경우
```bash
# 로그 확인
docker logs --tail 50 ai-chat-rag

# 메모리 제한 조정
docker update --memory="12g" ai-chat-rag

# 재시작
docker compose restart
```

### 응답이 너무 느린 경우
```bash
# 캐시 상태 확인
docker exec ai-chat-rag ls -la /app/cache/

# 리소스 할당 확인
docker inspect ai-chat-rag | grep -i cpu
docker inspect ai-chat-rag | grep -i memory
```

### 완전 초기화
```bash
# 모든 컨테이너 중지 & 제거
docker compose down -v

# 시스템 정리
docker system prune -a

# 다시 시작
docker compose up --build
```

---

## 📊 성능 기준값

### 정상 범위
- **초기 로딩**: 2-3분
- **검색 응답**: 2-5초 (캐시 미스)
- **캐시 응답**: 0.1-0.5초
- **메모리**: 8-12GB
- **CPU**: 40-60% (추론 시)

### 최적화 팁
1. **캐시 활용**: 같은 질문 반복 시 빨라짐
2. **메모리 여유**: 16GB 이상 권장
3. **GPU 사용**: CUDA 지원 시 2-3배 빨라짐

---

## 🎬 실제 사용 예시

### 1. Docker 실행 후 모니터링
```bash
# 터미널 1: Docker 실행
docker compose up --build

# 터미널 2: 로그 모니터링
docker compose logs -f --tail=50

# 터미널 3: 리소스 모니터링
watch -n 1 docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# 터미널 4: 상태 체크
while true; do docker ps; sleep 5; done
```

### 2. 브라우저에서 확인
- Tab 1: http://localhost:8501 (메인 앱)
- Tab 2: http://localhost:3000 (Grafana)
- Tab 3: 개발자 도구 (F12) - 네트워크 탭

---

*모니터링은 시스템 건강을 지키는 첫걸음입니다! 🏥*