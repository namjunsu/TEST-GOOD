# 🎯 신규 PC 설치 순서 (완벽 가이드)

> **현재 상황**: Windows PC에 아무것도 설치 안 됨
> **목표**: 이전 PC의 WSL 환경 완벽 재현
> **소요 시간**: 약 35분

---

## 📖 문서 가이드

이 폴더에는 여러 가이드 문서가 있습니다. **상황에 맞게 선택**하세요:

### 🚀 빠르게 시작하고 싶다면
→ **[🚀_지금_바로_시작.txt](🚀_지금_바로_시작.txt)** (3단계로 끝!)

### 📖 자세한 설명을 보고 싶다면
→ **[새PC_완벽설치.md](새PC_완벽설치.md)** (단계별 상세 설명)

### 🔧 문제가 생겼다면
→ **[문제해결.md](문제해결.md)** (트러블슈팅)

### 📚 기존 문서들
- [README.md](README.md) - 프로젝트 소개
- [START_HERE.md](START_HERE.md) - 이전 가이드 (WSL → WSL)
- [WSL_설치_가이드.md](WSL_설치_가이드.md) - WSL 상세 가이드

---

## ⚡ 초간단 3단계 (복사-붙여넣기만!)

### 1️⃣ WSL 설치 (PowerShell 관리자 권한)
```powershell
wsl --install
Restart-Computer
```
재시작 후 Ubuntu에서 사용자 이름/비밀번호 설정

### 2️⃣ 환경 설정 (Ubuntu 터미널)
```bash
# 이 파일의 위치로 이동
cd /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT

# 환경 설정 스크립트 실행
bash 2_WSL_환경설정.sh
```

### 3️⃣ 프로젝트 설치 (Ubuntu 터미널)
```bash
# 프로젝트 설치 스크립트 실행
bash 3_프로젝트_설치.sh
```

**끝!** 웹 브라우저에서 `http://localhost:8501` 열기

---

## 🛠️ 준비된 자동화 스크립트

### Windows용 (PowerShell)
- **[1_WSL_설치.ps1](1_WSL_설치.ps1)** - WSL 자동 설치
  - 관리자 권한 확인
  - WSL 설치 상태 확인
  - 자동 설치 및 재시작

### Linux용 (Bash)
- **[2_WSL_환경설정.sh](2_WSL_환경설정.sh)** - 환경 자동 설정
  - 시스템 업데이트
  - Python 3.10 설치
  - Tesseract OCR 설치

- **[3_프로젝트_설치.sh](3_프로젝트_설치.sh)** - 프로젝트 복사 및 설치
  - Windows → WSL 복사
  - 권한 설정
  - 자동 의존성 설치

- **[SETUP_NEW_PC.sh](SETUP_NEW_PC.sh)** - 의존성 자동 설치
  - 가상환경 생성
  - 패키지 17개 설치
  - 시스템 테스트

---

## 📋 상세 설치 순서

### PART 1: WSL2 설치

#### 방법 A: 자동 스크립트 (권장)
```powershell
# PowerShell 관리자 권한으로
cd "C:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT"
.\1_WSL_설치.ps1
```

#### 방법 B: 수동 설치
```powershell
# PowerShell 관리자 권한으로
wsl --install
Restart-Computer
```

---

### PART 2: Ubuntu 초기 설정

재시작 후 Ubuntu 창이 자동으로 열립니다:

```
Enter new UNIX username: wnstn4647
New password: [비밀번호 입력]
Retype new password: [비밀번호 재입력]
```

**중요**: 비밀번호는 화면에 안 보여도 입력됩니다!

---

### PART 3: 환경 설정

#### 방법 A: 자동 스크립트 (권장)
```bash
# Ubuntu 터미널에서
cd /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT
bash 2_WSL_환경설정.sh
```

#### 방법 B: 수동 설치
```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 도구
sudo apt install -y build-essential wget curl git unzip software-properties-common

# Python 3.10
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev python3-pip

# Tesseract OCR
sudo apt install -y tesseract-ocr tesseract-ocr-kor libtesseract-dev poppler-utils
```

---

### PART 4: 프로젝트 설치

#### 방법 A: 자동 스크립트 (권장)
```bash
# Ubuntu 터미널에서
cd /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT
bash 3_프로젝트_설치.sh
```

이 스크립트가 자동으로:
1. Windows → WSL 복사
2. 권한 설정
3. SETUP_NEW_PC.sh 실행 (선택 가능)

#### 방법 B: 수동 설치
```bash
# 프로젝트 복사
cp -r "/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT" ~/AI-CHAT
cd ~/AI-CHAT

# 권한 설정
chmod +x *.sh
sudo chown -R $USER:$USER ~/AI-CHAT

# 의존성 설치
bash SETUP_NEW_PC.sh
```

---

### PART 5: 실행

```bash
cd ~/AI-CHAT
source .venv/bin/activate
streamlit run web_interface.py --server.port 8501
```

브라우저에서 `http://localhost:8501` 열기

---

## ✅ 설치 확인 체크리스트

설치가 제대로 되었는지 확인하세요:

### 1. WSL 설치 확인
```powershell
# PowerShell에서
wsl --list --verbose
```
출력에 `VERSION 2` 확인

### 2. Ubuntu 버전 확인
```bash
# Ubuntu에서
lsb_release -a
```
Ubuntu 20.04 또는 22.04 권장

### 3. Python 확인
```bash
python3.10 --version
```
Python 3.10.x 출력

### 4. Tesseract 확인
```bash
tesseract --version
tesseract --list-langs | grep kor
```
'kor'이 목록에 있어야 함

### 5. 프로젝트 파일 확인
```bash
ls ~/AI-CHAT
```
다음 파일들이 보여야 함:
- web_interface.py
- requirements.txt
- docs/ 폴더
- .env 파일

### 6. 가상환경 확인
```bash
ls ~/AI-CHAT/.venv
```
.venv 폴더 존재 확인

### 7. 시스템 테스트
```bash
cd ~/AI-CHAT
source .venv/bin/activate
python3 test_system.py
```
"✅ 모든 테스트 통과" 메시지 확인

### 8. 웹 실행 확인
```bash
streamlit run web_interface.py --server.port 8501
```
브라우저에서 http://localhost:8501 열림

### 9. 검색 테스트
웹 페이지에서 "조명" 검색 → 결과 나옴

### 10. AI 답변 테스트
"상암 스튜디오 조명 소모품은?" 질문 → 답변 생성됨

---

## 🚨 자주 발생하는 문제

### 문제 1: "wsl 명령어를 찾을 수 없습니다"
**원인**: Windows 버전이 오래됨
**해결**: Windows 업데이트 (Build 19041 이상 필요)

### 문제 2: WSL 버전이 1임
**해결**:
```powershell
wsl --set-version Ubuntu 2
```

### 문제 3: "가상화를 사용할 수 없습니다"
**원인**: BIOS에서 가상화 비활성화
**해결**: 재부팅 → BIOS 진입 → Intel VT-x 또는 AMD-V 활성화

### 문제 4: Python 패키지 설치 실패
**해결**:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 문제 5: Tesseract 한글 인식 안 됨
**해결**:
```bash
sudo apt install tesseract-ocr-kor
```

### 문제 6: 파일 복사가 너무 느림
**해결**: tar 압축 사용
```bash
# Windows에서
cd "C:\Users\wnstn\OneDrive\Desktop\AI"
tar -czf AI-CHAT.tar.gz AI-CHAT

# Ubuntu에서
cp /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT.tar.gz ~
tar -xzf AI-CHAT.tar.gz
```

### 문제 7: 포트 8501이 이미 사용 중
**해결**:
```bash
pkill -f streamlit
streamlit run web_interface.py --server.port 8501
```

### 문제 8: 완전히 막힘 - 긴급 복구
```bash
# 모든 프로세스 종료
pkill -f python
pkill -f streamlit

# 가상환경 삭제
cd ~/AI-CHAT
rm -rf .venv

# 재설치
bash SETUP_NEW_PC.sh
```

---

## 💡 유용한 팁

### 1. Windows에서 WSL 폴더 접근
Windows 탐색기 주소창에:
```
\\wsl$\Ubuntu\home\wnstn4647\AI-CHAT
```

### 2. WSL에서 Windows 탐색기 열기
```bash
explorer.exe .
```

### 3. VSCode에서 WSL 프로젝트 열기
```bash
cd ~/AI-CHAT
code .
```

### 4. 자동 시작 스크립트
```bash
cd ~/AI-CHAT
bash start_ai_chat.sh
```

### 5. WSL 메모리 제한 (선택사항)
`C:\Users\wnstn\.wslconfig` 파일 생성:
```ini
[wsl2]
memory=8GB
processors=8
```

### 6. WSL 재시작
```powershell
wsl --shutdown
wsl
```

### 7. 백업 만들기
```bash
cd ~/AI-CHAT
bash QUICK_MIGRATION.sh
```

---

## 📞 추가 도움말

### 상세 가이드
- [새PC_완벽설치.md](새PC_완벽설치.md) - 단계별 상세 설명
- [WSL_설치_가이드.md](WSL_설치_가이드.md) - WSL 전문 가이드

### 문제 해결
- [문제해결.md](문제해결.md) - 트러블슈팅
- [FOLDER_GUIDE.md](FOLDER_GUIDE.md) - 폴더 구조 설명

### 프로젝트 정보
- [README.md](README.md) - 프로젝트 소개
- [QUALITY_STATUS.md](QUALITY_STATUS.md) - 답변 품질 상태

---

## 🎯 다음 단계

설치가 완료되면:

1. **정기 백업 설정**
   ```bash
   bash QUICK_MIGRATION.sh
   ```

2. **문서 추가**
   - Windows: `C:\Users\wnstn\OneDrive\Desktop\AI\AI-CHAT\docs\`에 PDF 추가
   - WSL에서 자동 인덱싱

3. **성능 조정**
   - `.env` 파일에서 설정 변경
   - GPU/CPU 최적화

---

**작성일**: 2025-10-14
**환경**: Windows 11 + WSL2 + Ubuntu 22.04
**소요 시간**: 약 35분
**난이도**: 초급 (복사-붙여넣기만!)

**이제 시작하세요! 🚀**
