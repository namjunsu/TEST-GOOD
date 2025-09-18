@echo off
setlocal enabledelayedexpansion

REM AI-CHAT-V3 자동 설치 스크립트 (Windows용)
REM 사용법: setup.bat을 우클릭하여 "관리자 권한으로 실행"

echo.
echo 🚀 AI-CHAT-V3 자동 설치를 시작합니다...
echo ==================================
echo.

REM 관리자 권한 확인
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ❌ 관리자 권한이 필요합니다.
    echo 이 스크립트를 우클릭하여 "관리자 권한으로 실행"을 선택해주세요.
    pause
    exit /b 1
)

REM 1. Python 설치 확인
echo ℹ️  Python 설치 확인 중...
python --version >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ❌ Python이 설치되어 있지 않습니다.
    echo 🌐 Python 3.9+ 다운로드 페이지를 열겠습니다...
    start https://www.python.org/downloads/
    echo 설치 후 이 스크립트를 다시 실행해주세요.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo ✅ Python !PYTHON_VERSION! 확인됨
)

REM 2. Git 설치 확인
echo ℹ️  Git 설치 확인 중...
git --version >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ❌ Git이 설치되어 있지 않습니다.
    echo 🌐 Git 다운로드 페이지를 열겠습니다...
    start https://git-scm.com/download/win
    echo 설치 후 이 스크립트를 다시 실행해주세요.
    pause
    exit /b 1
) else (
    echo ✅ Git 설치 확인됨
)

REM 3. 프로젝트 디렉토리 설정
set PROJECT_DIR=%USERPROFILE%\AI-CHAT-V3
echo ℹ️  프로젝트 디렉토리 설정: %PROJECT_DIR%

if exist "%PROJECT_DIR%" (
    echo ⚠️  기존 디렉토리가 있습니다. 백업 중...
    set BACKUP_DIR=%PROJECT_DIR%.backup.%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    set BACKUP_DIR=!BACKUP_DIR: =0!
    move "%PROJECT_DIR%" "!BACKUP_DIR!" >nul
)

mkdir "%PROJECT_DIR%"
cd /d "%PROJECT_DIR%"
echo ✅ 프로젝트 디렉토리 생성 완료

REM 4. 마이그레이션 파일 복원
echo ℹ️  마이그레이션 파일 복원 중...

REM 스크립트가 있는 디렉토리에서 파일 복사
set SCRIPT_DIR=%~dp0

if exist "%SCRIPT_DIR%core" (
    xcopy "%SCRIPT_DIR%core\*" "%PROJECT_DIR%" /y /q >nul
    xcopy "%SCRIPT_DIR%rag_system" "%PROJECT_DIR%\rag_system\" /e /i /y /q >nul
    xcopy "%SCRIPT_DIR%docs" "%PROJECT_DIR%\docs\" /e /i /y /q >nul
    xcopy "%SCRIPT_DIR%config\*" "%PROJECT_DIR%" /y /q >nul
    echo ✅ 마이그레이션 파일 복원 완료
) else (
    echo ❌ 마이그레이션 파일을 찾을 수 없습니다.
    echo setup.bat와 같은 디렉토리에 core/, rag_system/, docs/, config/ 폴더가 있는지 확인하세요.
    pause
    exit /b 1
)

REM 5. Python 가상환경 설정
echo ℹ️  Python 가상환경 생성 중...
python -m venv ai-chat-env
if %errorLevel% NEQ 0 (
    echo ❌ 가상환경 생성 실패
    pause
    exit /b 1
)

call ai-chat-env\Scripts\activate.bat
echo ✅ 가상환경 생성 완료

REM 6. Python 패키지 설치
echo ℹ️  Python 패키지 설치 중... (시간이 걸릴 수 있습니다)
python -m pip install --upgrade pip setuptools wheel

if exist "requirements.txt" (
    pip install -r requirements.txt
    if %errorLevel% NEQ 0 (
        echo ❌ 패키지 설치 실패
        pause
        exit /b 1
    )
    echo ✅ 패키지 설치 완료
) else (
    echo ❌ requirements.txt 파일을 찾을 수 없습니다.
    pause
    exit /b 1
)

REM 7. 모델 디렉토리 생성
echo ℹ️  모델 디렉토리 생성 중...
mkdir models >nul 2>&1
echo ✅ 모델 디렉토리 생성 완료

REM 8. 모델 파일 다운로드 안내
echo.
echo ⚠️  모델 파일 다운로드 필요 (약 4.4GB)
echo Windows에서는 수동 다운로드를 권장합니다:
echo.
echo 1. 브라우저에서 다음 링크를 열어 다운로드:
echo    https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/tree/main
echo.
echo 2. 다음 2개 파일을 models/ 폴더에 저장:
echo    - qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
echo    - qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf
echo.
set /p DOWNLOAD_MANUAL="수동으로 다운로드하시겠습니까? (Y/n): "
if /i "!DOWNLOAD_MANUAL!" == "Y" (
    start https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/tree/main
    echo 다운로드 완료 후 아무 키나 누르세요...
    pause >nul
) else (
    echo ℹ️  자동 다운로드 시도 중... (시간이 오래 걸릴 수 있습니다)
    
    REM PowerShell을 사용한 다운로드
    powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf' -OutFile 'models\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf' -UseBasicParsing }"
    
    powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf' -OutFile 'models\qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf' -UseBasicParsing }"
    
    echo ✅ 모델 다운로드 완료
)

REM 9. 환경변수 파일 생성
echo ℹ️  .env 파일 생성 중...
(
echo MODEL_PATH=./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
echo DB_DIR=./rag_system/db
echo LOG_DIR=./rag_system/logs
echo API_KEY=broadcast-tech-rag-2025
echo STREAMLIT_SERVER_PORT=8501
) > .env
echo ✅ .env 파일 생성 완료

REM 10. 로그 디렉토리 생성
echo ℹ️  로그 디렉토리 생성 중...
mkdir rag_system\logs >nul 2>&1
mkdir rag_system\db >nul 2>&1
echo ✅ 로그 디렉토리 생성 완료

REM 11. 인덱스 구축
echo ℹ️  문서 인덱싱 시작... (시간이 걸릴 수 있습니다)
python build_index.py
if %errorLevel% NEQ 0 (
    echo ❌ 인덱싱 실패
    pause
    exit /b 1
)
echo ✅ 인덱싱 완료

REM 12. 시스템 테스트
echo ℹ️  시스템 테스트 중...
python -c "import sys; sys.path.append('.'); from perfect_rag import PerfectRAG; rag = PerfectRAG(); print('시스템 테스트 성공')"
if %errorLevel% NEQ 0 (
    echo ❌ 시스템 테스트 실패
    pause
    exit /b 1
)
echo ✅ 시스템 테스트 통과

REM 13. 실행 배치 파일 생성
echo ℹ️  실행 배치 파일 생성 중...
(
echo @echo off
echo cd /d "%%~dp0"
echo call ai-chat-env\Scripts\activate.bat
echo echo 🚀 AI-CHAT-V3 웹 인터페이스를 시작합니다...
echo echo 브라우저에서 http://localhost:8501 을 열어주세요
echo streamlit run web_interface.py
echo pause
) > run_ai_chat.bat
echo ✅ 실행 배치 파일 생성 완료

REM 14. 설치 완료
echo.
echo 🎉 AI-CHAT-V3 설치가 완료되었습니다!
echo ==================================
echo.
echo 📁 설치 위치: %PROJECT_DIR%
echo.
echo 🚀 시스템 실행 방법:
echo 1. run_ai_chat.bat 더블클릭
echo.
echo 2. 수동 실행:
echo    - 명령 프롬프트에서:
echo      cd %PROJECT_DIR%
echo      ai-chat-env\Scripts\activate.bat
echo      streamlit run web_interface.py
echo.
echo 🌐 접속 주소: http://localhost:8501
echo.
echo 📚 도움말:
echo    - 마이그레이션 가이드: MIGRATION_GUIDE.md
echo    - 사용법: README.md
echo    - 개발 가이드: CLAUDE.md
echo.
echo ⚠️  주의사항:
echo    - 가상환경(ai-chat-env) 활성화 필요
echo    - Windows Defender에서 차단될 수 있음 (허용 설정)
echo    - 8501 포트가 사용 중이면 8502 포트 사용
echo.
echo ✅ 설치 스크립트 실행 완료!

REM 자동 실행 여부 묻기
echo.
set /p AUTO_RUN="지금 바로 웹 인터페이스를 실행하시겠습니까? (Y/n): "
if /i "!AUTO_RUN!" == "Y" (
    echo ℹ️  웹 인터페이스 실행 중...
    echo 브라우저에서 http://localhost:8501 을 열어주세요
    echo 종료하려면 Ctrl+C를 누르세요
    streamlit run web_interface.py
)

pause