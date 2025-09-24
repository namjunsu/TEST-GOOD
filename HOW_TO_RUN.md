# 🚀 AI-CHAT 실행 방법 (자세한 가이드)

## 📋 사전 준비사항

### 필수 설치 프로그램:
- **Python 3.9 이상**
- **Docker Desktop** (Docker 실행 시)
- **CUDA 12.1** (GPU 사용 시)

---

## 🔧 방법 1: 로컬에서 직접 실행

### 1단계: Python 패키지 설치
```bash
# 가상환경 생성 (선택사항, 권장)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements_updated.txt
```

### 2단계: 환경 변수 설정
```bash
# .env 파일 확인 (이미 있음)
cat .env

# 필요시 수정
nano .env
```

### 3단계: Streamlit 실행
```bash
# 메인 웹 인터페이스 실행
streamlit run web_interface.py

# 또는 포트 지정
streamlit run web_interface.py --server.port 8501
```

### 4단계: 브라우저 접속
```
http://localhost:8501
```

### ⚠️ 첫 실행 시 주의사항:
- **첫 로딩 2-3분 소요** (480개 PDF 메타데이터 구축)
- **메모리 최소 16GB 필요**
- **GPU 있으면 자동 활용**

---

## 🐳 방법 2: Docker로 실행 (권장)

### 1단계: Docker 확인
```bash
# Docker 설치 확인
docker --version
docker compose version

# Docker 실행 중인지 확인
docker ps
```

### 2단계: Docker 이미지 빌드 & 실행
```bash
# 이미지 빌드하고 실행 (첫 실행)
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 로그 실시간 모니터링
docker compose logs -f

# 특정 서비스만 로그 보기
docker compose logs -f rag-system
```

### 3단계: 브라우저 접속
```
http://localhost:8501
```

### 4단계: 모니터링 & 관리
```bash
# 실행 중인 컨테이너 확인
docker ps

# 컨테이너 리소스 사용량 모니터링 (실시간)
docker stats

# 컨테이너 로그 실시간 확인
docker logs -f ai-chat-rag

# 컨테이너 내부 접속
docker exec -it ai-chat-rag /bin/bash

# 시스템 상태 확인
docker compose ps
```

### 5단계: 종료
```bash
# 종료
docker compose down

# 완전 정리 (볼륨 포함)
docker compose down -v
```

---

## 🔍 실행 확인 방법

### 정상 실행 시 콘솔 출력:
```
You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501

📚 시스템 초기화 중...
✅ 메타데이터 캐시 로드 완료
✅ 시스템 준비 완료!
```

### 사이드바에 표시되는 내용:
```
📂 문서 라이브러리
✅ 480개 문서 준비 완료
```

---

## ❗ 문제 해결

### 1. "ModuleNotFoundError" 오류
```bash
# requirements 재설치
pip install -r requirements_updated.txt
```

### 2. "AttributeError: 'Logger'" 오류
```bash
# Docker 재시작
docker compose restart

# 또는 브라우저 새로고침 (F5)
```

### 3. 메모리 부족
```bash
# 메모리 확인
free -h

# Docker 메모리 제한 조정
docker update --memory="8g" ai-chat-rag
```

### 4. 포트 사용 중
```bash
# 8501 포트 확인
lsof -i :8501

# 다른 포트로 실행
streamlit run web_interface.py --server.port 8502
```

---

## 📝 기본 사용법

### 1. 문서 검색
- 왼쪽 사이드바에서 문서 선택
- 또는 검색창에 키워드 입력
- 예: "DVR 관련 문서", "2020년 구매"

### 2. 질문하기
- 채팅창에 질문 입력
- Enter 또는 "전송" 버튼 클릭
- AI가 관련 문서를 찾아 답변

### 3. 캐시 관리
- 사이드바 하단 "캐시 초기화" 버튼
- 문제 발생 시 캐시 초기화 권장

---

## 🔧 고급 설정

### GPU 사용 설정
```python
# config.py에서 확인
USE_GPU = True  # GPU 자동 감지
GPU_MEMORY_FRACTION = 0.8  # GPU 메모리 사용량
```

### 로깅 레벨 조정
```python
# log_system.py에서 수정
logging.basicConfig(level=logging.INFO)  # DEBUG로 변경 가능
```

### 문서 폴더 변경
```python
# perfect_rag.py에서 수정
self.docs_dir = Path("docs")  # 다른 경로로 변경 가능
```

---

## 📊 모니터링 방법

### Docker 실행 시 모니터링
```bash
# 1. 실시간 로그 보기 (새 터미널에서)
docker compose logs -f --tail=50

# 2. CPU/메모리 사용량 모니터링
docker stats ai-chat-rag

# 3. 컨테이너 상태 확인
docker compose ps
```

### 로컬 실행 시 모니터링
```bash
# 1. Streamlit 로그 (실행 터미널에서 자동 표시)
# You can now view your Streamlit app in your browser.
# Local URL: http://localhost:8501

# 2. 시스템 로그 확인 (새 터미널)
tail -f logs/system.log

# 3. GPU 사용량 모니터링 (NVIDIA GPU)
nvidia-smi -l 1

# 4. 메모리 사용량 확인
watch -n 1 free -h
```

### 웹 UI에서 모니터링
1. **사이드바 상태 표시**
   - 문서 로딩 상태
   - 캐시 히트율
   - 응답 시간

2. **로그 확인**
   - 왼쪽 사이드바 하단
   - "시스템 로그" 섹션

## 📞 도움말

### 시스템 상태 확인
```bash
# Python 프로세스 확인
ps aux | grep streamlit

# Docker 상태 확인
docker ps -a

# 로그 파일 목록
ls -la logs/

# 최근 에러 확인
grep ERROR logs/system.log | tail -20
```

### 완전 초기화
```bash
# 캐시 삭제
rm -rf cache/ __pycache__/ .streamlit/

# Docker 초기화
docker system prune -a
```

---

## 📈 성능 모니터링 대시보드

### Grafana 대시보드 (Docker 사용 시)
```bash
# Grafana 접속 (Docker 실행 후)
http://localhost:3000

# 기본 로그인
ID: admin
PW: admin
```

### 주요 모니터링 지표
- **응답 시간**: 평균 2-5초 (캐시 히트 시 0.1초)
- **메모리 사용량**: 8-12GB (모델 로드 시)
- **GPU 사용률**: 40-60% (추론 시)
- **캐시 히트율**: 20-30% (사용 패턴에 따라)

---

## 💡 팁

1. **첫 실행은 느립니다** - 정상입니다!
2. **두 번째부터는 빠릅니다** - 캐시 덕분
3. **메모리 16GB 이상 권장**
4. **GPU 있으면 더 빠름**
5. **Chrome/Edge 브라우저 권장**
6. **모니터링으로 성능 체크**

---

*문제가 계속되면 README_FINAL.md 참조 또는 이슈 등록*