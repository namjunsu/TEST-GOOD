# AI-CHAT 자동 포트 포워딩 설정 스크립트
# WSL2 IP가 바뀌어도 자동으로 포트 포워딩을 업데이트합니다

Write-Host "=== AI-CHAT 포트 포워딩 설정 ===" -ForegroundColor Cyan

# 기존 포트 포워딩 규칙 삭제
Write-Host "기존 포트 포워딩 규칙 삭제 중..." -ForegroundColor Yellow
netsh interface portproxy delete v4tov4 listenport=8501 listenaddress=0.0.0.0 2>$null

# WSL2 IP 주소 가져오기
Write-Host "WSL2 IP 주소 확인 중..." -ForegroundColor Yellow
$wslIp = (wsl hostname -I).Trim().Split()[0]

if ([string]::IsNullOrEmpty($wslIp)) {
    Write-Host "ERROR: WSL2 IP 주소를 찾을 수 없습니다!" -ForegroundColor Red
    Write-Host "WSL이 실행 중인지 확인하세요." -ForegroundColor Red
    pause
    exit 1
}

Write-Host "WSL2 IP: $wslIp" -ForegroundColor Green

# 새 포트 포워딩 규칙 추가
Write-Host "포트 포워딩 규칙 추가 중..." -ForegroundColor Yellow
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=$wslIp

# 방화벽 규칙 확인 (없으면 추가)
Write-Host "방화벽 규칙 확인 중..." -ForegroundColor Yellow
$firewallRule = Get-NetFirewallRule -DisplayName "Streamlit AI-CHAT" -ErrorAction SilentlyContinue

if ($null -eq $firewallRule) {
    Write-Host "방화벽 규칙 추가 중..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName "Streamlit AI-CHAT" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow | Out-Null
    Write-Host "방화벽 규칙 추가 완료!" -ForegroundColor Green
} else {
    Write-Host "방화벽 규칙 이미 존재함" -ForegroundColor Green
}

# 현재 설정 확인
Write-Host "`n=== 현재 포트 포워딩 설정 ===" -ForegroundColor Cyan
netsh interface portproxy show v4tov4

# 접속 정보 출력
$hostIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" -and $_.IPAddress -notlike "192.168.*" -and $_.InterfaceAlias -notlike "*WSL*"} | Select-Object -First 1).IPAddress

Write-Host "`n=== 접속 정보 ===" -ForegroundColor Cyan
Write-Host "이 PC에서 접속: http://localhost:8501" -ForegroundColor White
if ($hostIp) {
    Write-Host "다른 PC에서 접속: http://$($hostIp):8501" -ForegroundColor Green
}
Write-Host "`n설정 완료!" -ForegroundColor Green
