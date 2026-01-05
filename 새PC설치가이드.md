# 🚀 AI-CHAT 새 PC 설치 가이드

> **초보자도 5분이면 설치 가능!**
> 외장하드에서 복사한 후 스크립트 하나만 실행하면 됩니다.

---

## 📋 설치 전 준비물

- ✅ AI-CHAT 백업 파일이 담긴 외장하드
- ✅ Ubuntu 20.04 이상 설치된 PC
- ✅ 인터넷 연결 (패키지 다운로드용)
- ✅ 관리자(sudo) 권한

---

## 🔧 설치 방법 (3단계)

### 1️⃣ 외장하드에서 파일 복사

```bash
# 1. 외장하드 연결 후 자동 마운트 확인
# 보통 /media/사용자명/... 경로에 자동 마운트됨

# 2. 백업 폴더 찾기
ls /media/*/AI-CHAT-backup-*

# 3. 홈 디렉토리로 복사 (예시)
cp -r /media/사용자명/외장하드명/AI-CHAT-backup-20250105-* ~/Desktop/AI-CHAT

# 4. 복사된 디렉토리로 이동
cd ~/Desktop/AI-CHAT
```

---

### 2️⃣ 자동 설치 스크립트 실행

```bash
# 실행 권한 확인 (이미 있으면 생략 가능)
chmod +x INSTALL_NEW_PC.sh

# 설치 시작!
./INSTALL_NEW_PC.sh
```

**설치 중 수행되는 작업:**
- ✅ 시스템 패키지 설치 (Python, Tesseract, Poppler 등)
- ✅ Python 가상환경 생성
- ✅ AI 라이브러리 설치 (vLLM, FAISS, Transformers 등)
- ✅ 환경 설정 파일(.env) 경로 자동 수정
- ✅ GPU 감지 및 설정

**예상 소요 시간:** 5~10분 (인터넷 속도에 따라 다름)

---

### 3️⃣ AI-CHAT 실행

```bash
# 1. 가상환경 활성화
source .venv/bin/activate

# 2. AI-CHAT 시작
./start_ai_chat.sh
```

**실행 후 접속:**
- 🌐 웹 인터페이스: http://localhost:8501
- 🔌 API 엔드포인트: http://localhost:7860

---

## 🛠️ 고급 설정 (선택사항)

### GPU 메모리 조정

GPU 메모리가 부족하거나 여유가 있다면 `.env` 파일 수정:

```bash
nano .env
```

다음 항목 조정:
```bash
# GPU 메모리 활용률 (기본: 0.90 = 90%)
VLLM_GPU_MEMORY_UTILIZATION=0.85  # 메모리 부족 시 0.7~0.85로 낮춤
VLLM_MAX_MODEL_LEN=32768          # 메모리 부족 시 16384로 낮춤
```

### CPU 코어 수 조정

CPU 코어 수에 맞게 설정:

```bash
# CPU 정보 확인
nproc

# .env 파일 수정
N_THREADS=20           # CPU 코어 수에 맞게 조정
PARALLEL_WORKERS=20    # 동시 처리 워커 수
```

---

## 🐛 문제 해결

### 1. "python3.10: command not found" 오류

```bash
# Python 3.10 수동 설치
sudo apt update
sudo apt install -y python3.10 python3.10-venv
```

### 2. "모델을 찾을 수 없습니다" 오류

```bash
# 모델 파일 확인
ls -lh ~/Desktop/AI-CHAT/models/

# 모델이 없다면 백업에서 다시 복사
cp -r /media/외장하드/AI-CHAT-backup-*/models ~/Desktop/AI-CHAT/
```

### 3. GPU를 인식하지 못함

```bash
# NVIDIA 드라이버 확인
nvidia-smi

# 설치되지 않았다면
sudo apt install nvidia-driver-535  # 또는 최신 버전
sudo reboot
```

### 4. 패키지 설치 실패

```bash
# 가상환경 재생성
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. 포트가 이미 사용 중

```bash
# 포트 사용 중인 프로세스 확인
sudo lsof -i :8501
sudo lsof -i :7860

# 프로세스 종료
kill -9 <프로세스ID>
```

---

## 📊 시스템 요구사항

### 최소 사양
- CPU: 4코어 이상
- RAM: 16GB
- 저장공간: 50GB (모델 포함)
- OS: Ubuntu 20.04+

### 권장 사양 (GPU 사용)
- GPU: NVIDIA RTX 3090 / A100 / H100 (24GB+ VRAM)
- CPU: 8코어 이상
- RAM: 32GB+
- 저장공간: 100GB (SSD 권장)

### 현재 백업된 설정 (H100 기준)
- LLM: Qwen2.5-72B-Instruct-AWQ (39GB)
- Embedding: multilingual-e5-large
- 최대 컨텍스트: 32K 토큰
- GPU 메모리 활용: 90% (72GB)

---

## 📞 추가 도움이 필요하신가요?

### 로그 확인
```bash
# 실시간 로그 보기
tail -f logs/app.log

# 최근 에러 확인
grep ERROR logs/app.log | tail -20
```

### 설정 파일 위치
- 환경 설정: `.env`
- 시작 스크립트: `start_ai_chat.sh`
- 모델 경로: `models/`
- 문서 경로: `docs/`

### 완전히 재설치
```bash
# 가상환경 삭제
rm -rf .venv

# 캐시/로그 삭제
rm -rf logs/* var/index/*

# 재설치
./INSTALL_NEW_PC.sh
```

---

## ✅ 설치 체크리스트

- [ ] 외장하드에서 AI-CHAT 폴더 복사 완료
- [ ] `INSTALL_NEW_PC.sh` 실행 완료
- [ ] 시스템 패키지 설치 완료
- [ ] Python 가상환경 생성 완료
- [ ] Python 패키지 설치 완료
- [ ] `.env` 파일 경로 자동 수정 완료
- [ ] `./start_ai_chat.sh` 실행 성공
- [ ] http://localhost:8501 접속 확인

모든 항목에 체크되면 설치 완료! 🎉

---

**최종 수정:** 2025-01-05
**작성자:** AI-CHAT 개발팀
