# 🐧 WSL2 설치 및 프로젝트 이전 완벽 가이드

> 이전 PC의 WSL 환경을 현재 Windows PC에 똑같이 재현하기

---

## 📋 목차
1. [WSL2 설치](#step-1-wsl2-설치)
2. [Ubuntu 배포판 설치](#step-2-ubuntu-배포판-설치)
3. [WSL2 기본 설정](#step-3-wsl2-기본-설정)
4. [Python 환경 구축](#step-4-python-환경-구축)
5. [Tesseract OCR 설치](#step-5-tesseract-ocr-설치)
6. [프로젝트 파일 이전](#step-6-프로젝트-파일-이전)
7. [의존성 설치](#step-7-의존성-설치)
8. [시스템 테스트](#step-8-시스템-테스트)
9. [웹 인터페이스 실행](#step-9-웹-인터페이스-실행)

---

## Step 1: WSL2 설치

### 1-1. PowerShell 관리자 권한으로 실행
1. Windows 검색창에서 "PowerShell" 입력
2. 우클릭 → "관리자 권한으로 실행"

### 1-2. WSL 설치 (가장 간단한 방법)
```powershell
wsl --install
```

이 명령어가 자동으로 해줍니다:
- WSL2 활성화
- 가상 머신 플랫폼 활성화
- Linux 커널 업데이트
- Ubuntu 배포판 설치 (기본값)

### 1-3. 컴퓨터 재시작
```powershell
Restart-Computer
```

---

## Step 2: Ubuntu 배포판 설치

### 2-1. 재시작 후 Ubuntu 자동 실행
- 재시작하면 Ubuntu 설치가 자동으로 계속됩니다
- 사용자 이름과 비밀번호를 설정하라는 메시지가 나옵니다

### 2-2. 사용자 계정 생성
```bash
# 사용자 이름 입력 (예: wnstn4647)
Enter new UNIX username: wnstn4647

# 비밀번호 입력 (입력해도 화면에 안 보입니다)
New password: [비밀번호 입력]
Retype new password: [비밀번호 재입력]
```

### 2-3. WSL 버전 확인
PowerShell에서 확인:
```powershell
wsl --list --verbose
```

출력 예시:
```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

VERSION이 2인지 확인! (1이면 WSL1입니다)

### 2-4. WSL1인 경우 WSL2로 변경
```powershell
wsl --set-version Ubuntu 2
```

---

## Step 3: WSL2 기본 설정

### 3-1. Ubuntu 터미널 실행
- Windows 검색창에서 "Ubuntu" 입력
- 또는 PowerShell에서: `wsl`

### 3-2. 시스템 업데이트
```bash
sudo apt update && sudo apt upgrade -y
```

### 3-3. 필수 도구 설치
```bash
sudo apt install -y \
    build-essential \
    wget \
    curl \
    git \
    unzip \
    software-properties-common
```

### 3-4. 홈 디렉토리 확인
```bash
pwd
# 출력: /home/wnstn4647 (또는 설정한 사용자 이름)
```

---

## Step 4: Python 환경 구축

### 4-1. Python 3.10 설치
```bash
# Python 3.10 저장소 추가
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Python 3.10 및 관련 패키지 설치
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    python3-pip
```

### 4-2. Python 버전 확인
```bash
python3.10 --version
# 출력: Python 3.10.x
```

### 4-3. Python 3.10을 기본으로 설정 (선택사항)
```bash
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
```

---

## Step 5: Tesseract OCR 설치

### 5-1. Tesseract 및 한글 언어팩 설치
```bash
sudo apt install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    libtesseract-dev
```

### 5-2. Poppler (PDF 렌더링) 설치
```bash
sudo apt install -y poppler-utils
```

### 5-3. Tesseract 버전 확인
```bash
tesseract --version
# 출력: tesseract 4.x.x 이상이면 OK
```

---

## Step 6: 프로젝트 파일 이전

### 6-1. Windows 경로를 WSL에서 접근하기
WSL에서 Windows 드라이브는 `/mnt/` 아래에 마운트됩니다:
- C 드라이브: `/mnt/c/`
- D 드라이브: `/mnt/d/`

현재 프로젝트 위치:
```
c:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT
```

WSL에서 접근:
```
/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT
```

### 6-2. WSL 홈 디렉토리로 프로젝트 복사
```bash
# 홈 디렉토리로 이동
cd ~

# 프로젝트 전체 복사 (이 명령어를 그대로 실행하세요!)
cp -r "/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT" ~/AI-CHAT

# 복사 완료 확인
cd ~/AI-CHAT
ls -la
```

### 6-3. 권한 설정 (중요!)
```bash
# 실행 스크립트 권한 부여
chmod +x *.sh

# 모든 파일 소유권 설정
sudo chown -R $USER:$USER ~/AI-CHAT
```

---

## Step 7: 의존성 설치

### 7-1. 자동 설치 스크립트 실행
```bash
cd ~/AI-CHAT
bash SETUP_NEW_PC.sh
```

이 스크립트가 자동으로:
1. Python 버전 확인
2. 가상환경 생성 (`.venv`)
3. pip 업그레이드
4. 모든 패키지 설치 (5-10분 소요)
5. 필수 파일 확인
6. 시스템 테스트

### 7-2. 수동 설치 (스크립트 실패시)
```bash
# 가상환경 생성
python3.10 -m venv .venv

# 가상환경 활성화
source .venv/bin/activate

# pip 업그레이드
pip install --upgrade pip setuptools wheel

# 의존성 설치
pip install -r requirements.txt
```

---

## Step 8: 시스템 테스트

### 8-1. 가상환경 활성화
```bash
cd ~/AI-CHAT
source .venv/bin/activate
```

프롬프트가 `(.venv)` 로 시작하면 성공!

### 8-2. 테스트 실행
```bash
python3 test_system.py
```

### 8-3. 예상 출력
```
🧪 Channel A RAG System - 전체 테스트
=====================================

✅ Python 버전: 3.10.x
✅ Tesseract OCR: 4.x.x
✅ 필수 파일 존재
✅ 모든 테스트 통과!
```

---

## Step 9: 웹 인터페이스 실행

### 9-1. Streamlit 실행
```bash
cd ~/AI-CHAT
source .venv/bin/activate
streamlit run web_interface.py --server.port 8501
```

### 9-2. 브라우저에서 접속
```
http://localhost:8501
```

### 9-3. 정상 동작 확인
1. 웹 페이지가 열리는지 확인
2. "빠른 검색" 테스트: "조명" 검색
3. "AI 답변" 테스트: "상암 스튜디오 조명 소모품은?"

---

## 🚨 자주 발생하는 문제

### 문제 1: "wsl --install" 명령어가 안 됨
**해결**: Windows 업데이트 필요
```powershell
# Windows 버전 확인 (Build 19041 이상 필요)
winver

# Windows 업데이트 실행
# 설정 → Windows 업데이트 → 업데이트 확인
```

### 문제 2: WSL 실행시 "참조된 어셈블리를 찾을 수 없습니다"
**해결**: Windows 기능 수동 활성화
```powershell
# PowerShell 관리자 권한으로:
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 재시작 후:
wsl --set-default-version 2
```

### 문제 3: pip install 중 오류 발생
**해결**: 개별 패키지 설치
```bash
# 문제가 되는 패키지만 먼저 설치
pip install llama-cpp-python==0.2.32

# 나머지 설치
pip install -r requirements.txt
```

### 문제 4: Tesseract 한글 인식 안 됨
**해결**: 언어팩 재설치
```bash
sudo apt install tesseract-ocr-kor

# 설치된 언어 확인
tesseract --list-langs
# 'kor'이 목록에 있어야 함
```

### 문제 5: 파일 복사가 너무 느림
**해결**: Windows Terminal 사용 또는 tar 압축
```bash
# Windows에서 tar 압축
cd "c:\Users\wnstn\OneDrive\Desktop\AI"
tar -czf AI-CHAT.tar.gz AI-CHAT

# WSL에서 압축 해제
cd ~
cp /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT.tar.gz .
tar -xzf AI-CHAT.tar.gz
```

---

## 💡 추가 팁

### WSL에서 Windows 프로그램 실행
```bash
# Windows의 VSCode에서 WSL 폴더 열기
code ~/AI-CHAT

# Windows 탐색기에서 현재 폴더 열기
explorer.exe .
```

### WSL 메모리 제한 설정 (선택사항)
WSL이 RAM을 너무 많이 사용하면:
```powershell
# Windows에서: C:\Users\wnstn\.wslconfig 파일 생성
[wsl2]
memory=8GB
processors=8
```

### WSL 재시작
```powershell
wsl --shutdown
wsl
```

---

## ✅ 설치 완료 체크리스트

- [ ] WSL2 설치 완료 (`wsl --list --verbose`로 확인)
- [ ] Ubuntu 배포판 설치 완료
- [ ] Python 3.10 설치 완료 (`python3.10 --version`)
- [ ] Tesseract OCR 설치 완료 (`tesseract --version`)
- [ ] 프로젝트 파일 복사 완료 (`~/AI-CHAT` 폴더 존재)
- [ ] 가상환경 생성 완료 (`~/AI-CHAT/.venv` 폴더 존재)
- [ ] 의존성 설치 완료 (`pip list` 확인)
- [ ] 시스템 테스트 통과 (`python3 test_system.py`)
- [ ] 웹 인터페이스 실행 성공 (`http://localhost:8501`)

---

## 🎯 다음 단계

설치가 완료되었다면:

1. **자동 시작 스크립트 사용**
   ```bash
   cd ~/AI-CHAT
   bash start_ai_chat.sh
   ```

2. **문서 추가**
   - Windows: `c:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT\docs\`에 PDF 추가
   - WSL에서 자동 인덱싱됨

3. **백업 설정**
   ```bash
   bash QUICK_MIGRATION.sh
   # 백업 파일을 외장 하드에 복사
   ```

---

**작성일**: 2025-10-14
**프로젝트**: Channel A MEDIATECH RAG 시스템
**환경**: Windows 11 + WSL2 + Ubuntu 22.04
