@echo off
echo WSL2 네트워크 설정 중...

REM 기존 포트프록시 삭제 (있을 경우)
netsh interface portproxy delete v4tov4 listenport=8501 2>nul

REM WSL2 포트포워딩 설정
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=172.19.145.167

REM 방화벽 규칙 추가
netsh advfirewall firewall delete rule name="WSL2 Streamlit" 2>nul
netsh advfirewall firewall add rule name="WSL2 Streamlit" dir=in action=allow protocol=TCP localport=8501

echo 설정 완료! 이제 http://10.200.4.118:8501 로 접속 가능합니다.
pause