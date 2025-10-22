# 🎯 새 PC에서 완벽 설치 (WSL부터 끝까지)

> **상황**: Windows PC에 아무것도 없는 상태 → WSL 설치부터 프로젝트 실행까지

---

## ⏱️ 예상 소요 시간
- **WSL 설치**: 10분 (재시작 포함)
- **환경 설정**: 5분
- **프로젝트 이전**: 10분 (파일 크기에 따라)
- **의존성 설치**: 10분
- **총 소요**: 약 35분

---

## 📋 준비물
- [ ] 이 폴더가 있는 USB 또는 외장하드
- [ ] 인터넷 연결
- [ ] 관리자 권한

---

# PART 1: WSL2 설치 (10분)

## Step 1: PowerShell 열기

1. **Windows 키** 누르기
2. **"PowerShell"** 입력
3. **우클릭** → **"관리자 권한으로 실행"**

## Step 2: WSL 설치 (한 줄이면 끝!)

PowerShell에 이 명령어 **복사-붙여넣기**:

```powershell
wsl --install
```

이게 끝입니다! 이 명령어가 자동으로:
- ✅ WSL2 활성화
- ✅ 가상 머신 기능 활성화
- ✅ Linux 커널 설치
- ✅ Ubuntu 설치

**출력 예시**:
```
설치 중: 가상 머신 플랫폼
설치 중: Linux용 Windows 하위 시스템
다운로드 중: WSL 커널
설치 중: Ubuntu
다시 시작해야 변경 내용이 적용됩니다.
```

## Step 3: 컴퓨터 재시작

```powershell
Restart-Computer
```

또는 수동으로 재시작하세요.

---

## Step 4: Ubuntu 초기 설정 (재시작 후)

재시작하면 **Ubuntu 창이 자동으로** 열립니다.

### 4-1. 사용자 이름 입력
```
Enter new UNIX username: wnstn4647
```
(원하는 이름 입력, 영문 소문자만)

### 4-2. 비밀번호 설정
```
New password: [비밀번호 입력]
Retype new password: [다시 입력]
```
⚠️ **중요**: 입력해도 화면에 안 보입니다! (정상)

### 4-3. 완료 확인
```
Installation successful!
```

이 메시지가 나오면 성공! 🎉

---

## Step 5: WSL 버전 확인

**새 PowerShell** 창 열고:
```powershell
wsl --list --verbose
```

**출력**:
```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

👉 **VERSION이 2**인지 확인!

만약 1이면:
```powershell
wsl --set-version Ubuntu 2
```

---

# PART 2: 환경 설정 (5분)

## Step 6: Ubuntu 터미널 열기

**방법 1**: Windows 검색창에서 "Ubuntu" 입력
**방법 2**: PowerShell에서 `wsl` 입력

## Step 7: 시스템 업데이트

아래 명령어를 **복사-붙여넣기**:

```bash
sudo apt update && sudo apt upgrade -y
```

비밀번호 입력 (Step 4에서 설정한 것)

## Step 8: 필수 도구 설치

```bash
sudo apt install -y build-essential wget curl git unzip software-properties-common
```

## Step 9: Python 3.10 설치

```bash
# Python 3.10 저장소 추가
sudo add-apt-repository ppa:deadsnakes/ppa -y

# 업데이트
sudo apt update

# Python 3.10 설치
sudo apt install -y python3.10 python3.10-venv python3.10-dev python3-pip

# 버전 확인
python3.10 --version
```

**출력**: `Python 3.10.x` (x는 아무 숫자나 OK)

## Step 10: Tesseract OCR 설치

```bash
# Tesseract + 한글 언어팩 설치
sudo apt install -y tesseract-ocr tesseract-ocr-kor libtesseract-dev poppler-utils

# 버전 확인
tesseract --version
```

**✅ 환경 설정 완료!**

---

# PART 3: 프로젝트 이전 (10분)

## Step 11: 현재 위치 확인

```bash
pwd
```

**출력**: `/home/wnstn4647` (또는 설정한 사용자 이름)

## Step 12: Windows 폴더 경로 확인

현재 프로젝트 위치:
```
C:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT
```

WSL에서는:
```
/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT
```

## Step 13: 프로젝트 복사

### 방법 1: 직접 복사 (간단)

```bash
# 홈 디렉토리로 전체 복사
cp -r "/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT" ~/AI-CHAT

# 복사 완료 확인
cd ~/AI-CHAT
ls -la
```

### 방법 2: tar 압축 (빠름, 대용량 추천)

**Windows PowerShell에서**:
```powershell
cd "C:\Users\wnstn\OneDrive\Desktop\AI"
tar -czf AI-CHAT.tar.gz AI-CHAT
```

**Ubuntu에서**:
```bash
cd ~
cp /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT.tar.gz .
tar -xzf AI-CHAT.tar.gz
cd AI-CHAT
```

## Step 14: 권한 설정

```bash
# 스크립트 실행 권한
chmod +x *.sh

# 소유권 설정
sudo chown -R $USER:$USER ~/AI-CHAT
```

**✅ 프로젝트 이전 완료!**

---

# PART 4: 의존성 설치 (10분)

## Step 15: 자동 설치 스크립트 실행

```bash
cd ~/AI-CHAT
bash SETUP_NEW_PC.sh
```

이 스크립트가 **자동으로**:

1. ✅ Python 버전 확인
2. ✅ 가상환경 생성 (`.venv`)
3. ✅ pip 업그레이드
4. ✅ 패키지 17개 설치 (5-10분)
   - streamlit
   - pdfplumber
   - faiss-cpu
   - sentence-transformers
   - llama-cpp-python
   - 등등...
5. ✅ 필수 파일 확인
6. ✅ 시스템 테스트

**예상 출력**:
```
🚀 AI-CHAT 신규 PC 자동 설치 시작
==================================

📋 Step 1: Python 버전 확인
─────────────────────────────────
✅ Python 버전: 3.10.x

📋 Step 2: 필수 시스템 패키지 확인
─────────────────────────────────
✅ Tesseract OCR: tesseract 4.x.x

📋 Step 3: 가상환경 생성
─────────────────────────────────
✅ 가상환경 생성 완료

📋 Step 4: pip 업그레이드
─────────────────────────────────
✅ pip 업그레이드 완료

📋 Step 5: 패키지 설치 (5-10분 소요)
─────────────────────────────────
[1/17] 설치 중: streamlit==1.29.0 ... ✅
[2/17] 설치 중: python-dotenv==1.0.0 ... ✅
...
✅ 모든 패키지 설치 완료

📋 Step 6: 필수 파일 확인
─────────────────────────────────
✅ web_interface.py
✅ hybrid_chat_rag_v2.py
✅ docs/ 폴더 (PDF: 480개)

==================================
✅ 설치 완료!
==================================
```

---

# PART 5: 실행 및 테스트 (5분)

## Step 16: 가상환경 활성화

```bash
cd ~/AI-CHAT
source .venv/bin/activate
```

프롬프트가 `(.venv)` 로 시작하면 성공!

```
(.venv) wnstn4647@DESKTOP:~/AI-CHAT$
```

## Step 17: 시스템 테스트

```bash
python3 test_system.py
```

**예상 출력**:
```
🧪 Channel A RAG System - 전체 테스트
=====================================

✅ Python 버전: 3.10.x
✅ 모든 라이브러리 설치됨
✅ Tesseract OCR: 4.x.x
✅ 필수 파일 존재
✅ everything_index.db (480개 문서)
✅ metadata.db (480개 메타데이터)
✅ 모든 테스트 통과!
```

## Step 18: 웹 인터페이스 실행

```bash
streamlit run web_interface.py --server.port 8501
```

**출력**:
```
You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

## Step 19: 브라우저에서 접속

**Windows 브라우저**에서:
```
http://localhost:8501
```

**✅ 설치 완료!** 🎉

---

# 🧪 동작 확인

## 테스트 1: 빠른 검색
1. 상단 "빠른 검색" 선택
2. 검색어 입력: `조명`
3. 결과가 나오는지 확인

## 테스트 2: AI 답변
1. "AI 답변 생성" 선택
2. 질문 입력: `상암 스튜디오 조명 소모품은?`
3. 답변 생성 확인 (30-60초 소요)

---

# 🚨 문제 발생시

## 문제 1: "wsl --install" 명령어 없음

**원인**: Windows 버전이 너무 오래됨

**해결**:
```powershell
# Windows 버전 확인
winver

# Build 19041 이상 필요
# 없으면 Windows 업데이트 실행
```

---

## 문제 2: WSL 버전이 1임

**해결**:
```powershell
wsl --set-version Ubuntu 2
```

---

## 문제 3: Python 패키지 설치 실패

**해결**:
```bash
# pip 업그레이드
pip install --upgrade pip

# 문제 패키지만 먼저 설치
pip install llama-cpp-python==0.2.32

# 나머지 설치
pip install -r requirements.txt
```

---

## 문제 4: 파일 복사가 너무 느림

**해결**: tar 압축 사용 (위 Step 13 방법 2)

---

## 문제 5: Streamlit 실행 안 됨

**해결**:
```bash
# 기존 프로세스 종료
pkill -f streamlit

# 가상환경 재활성화
source .venv/bin/activate

# 재실행
streamlit run web_interface.py --server.port 8501
```

---

## 문제 6: 완전히 막힘

**긴급 복구**:
```bash
# 1. 모든 Python 프로세스 종료
pkill -f python
pkill -f streamlit

# 2. 가상환경 삭제
cd ~/AI-CHAT
rm -rf .venv

# 3. 재설치
bash SETUP_NEW_PC.sh
```

---

# 💡 유용한 팁

## Tip 1: Windows에서 WSL 폴더 접근

**Windows 탐색기** 주소창에:
```
\\wsl$\Ubuntu\home\wnstn4647\AI-CHAT
```

또는 Ubuntu에서:
```bash
explorer.exe .
```

---

## Tip 2: VSCode에서 WSL 폴더 열기

Ubuntu에서:
```bash
cd ~/AI-CHAT
code .
```

(VSCode가 자동으로 WSL 확장 설치)

---

## Tip 3: 자동 시작 스크립트

매번 명령어 치기 귀찮으면:
```bash
cd ~/AI-CHAT
bash start_ai_chat.sh
```

---

## Tip 4: WSL 메모리 제한

WSL이 RAM을 너무 많이 사용하면:

**Windows에서** `C:\Users\wnstn\.wslconfig` 파일 생성:
```ini
[wsl2]
memory=8GB
processors=8
```

저장 후 WSL 재시작:
```powershell
wsl --shutdown
wsl
```

---

## Tip 5: WSL 재시작

문제가 생기면:
```powershell
wsl --shutdown
wsl
```

---

# ✅ 최종 체크리스트

설치가 제대로 되었는지 확인:

- [ ] `wsl --list --verbose` → VERSION 2
- [ ] `python3.10 --version` → Python 3.10.x
- [ ] `tesseract --version` → tesseract 4.x.x
- [ ] `ls ~/AI-CHAT` → 프로젝트 파일 보임
- [ ] `ls ~/AI-CHAT/.venv` → 가상환경 존재
- [ ] `source .venv/bin/activate` → (.venv) 표시
- [ ] `python3 test_system.py` → ✅ 모든 테스트 통과
- [ ] `http://localhost:8501` → 웹 페이지 열림
- [ ] "조명" 검색 → 결과 나옴
- [ ] AI 답변 생성 → 답변 생성됨

**모두 체크되면 완벽! 🎉**

---

# 🎯 다음 단계

## 1. 백업 자동화

```bash
cd ~/AI-CHAT
bash QUICK_MIGRATION.sh
```

생성된 파일을 외장 하드에 복사해두기

## 2. 문서 추가

Windows에서 PDF 추가:
```
C:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT\docs\
```

WSL에서 자동 인덱싱됨 (재시작 불필요)

## 3. 성능 조정

`.env` 파일에서 설정 변경 가능:
- `N_THREADS`: CPU 코어 수
- `N_GPU_LAYERS`: GPU 사용량
- `N_CTX`: 컨텍스트 크기

---

**작성일**: 2025-10-14
**대상**: 신규 Windows PC
**환경**: Windows 11 + WSL2 + Ubuntu 22.04
**소요 시간**: 약 35분

**이제 시작하세요! 🚀**
