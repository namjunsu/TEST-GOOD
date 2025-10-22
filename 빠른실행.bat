@echo off
chcp 65001 > nul
echo ===================================
echo   AI-CHAT 빠른 실행
echo ===================================
echo.
echo 포트 포워딩 설정 중...
powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\wnstn4647\AI-CHAT\setup_port_forwarding.ps1"
echo.
echo 완료! 브라우저에서 http://localhost:8501 접속하세요.
echo.
pause
