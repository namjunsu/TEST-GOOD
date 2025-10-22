# AI-CHAT 자동 시작 설정 스크립트
# Windows 부팅 시 자동으로 포트 포워딩을 설정합니다

Write-Host "=== AI-CHAT 자동 시작 설정 ===" -ForegroundColor Cyan

# 스크립트 경로 설정
$scriptPath = "\\wsl.localhost\Ubuntu\home\wnstn4647\AI-CHAT\setup_port_forwarding.ps1"
$localScriptPath = "$env:USERPROFILE\AI-CHAT-PortForwarding.ps1"

# 스크립트를 Windows로 복사
Write-Host "포트 포워딩 스크립트 복사 중..." -ForegroundColor Yellow
Copy-Item $scriptPath $localScriptPath -Force

# 작업 스케줄러에 등록
Write-Host "작업 스케줄러에 등록 중..." -ForegroundColor Yellow

$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$localScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogon
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# 기존 작업 삭제
Unregister-ScheduledTask -TaskName "AI-CHAT Port Forwarding" -Confirm:$false -ErrorAction SilentlyContinue

# 새 작업 등록
Register-ScheduledTask -TaskName "AI-CHAT Port Forwarding" -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

Write-Host "`n설정 완료!" -ForegroundColor Green
Write-Host "Windows 로그인 시 자동으로 포트 포워딩이 설정됩니다." -ForegroundColor Green
Write-Host "`n지금 바로 포트 포워딩을 설정하려면 'setup_port_forwarding.ps1'을 실행하세요." -ForegroundColor Yellow
