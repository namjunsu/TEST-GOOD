# WSL 자동 설치 스크립트
# 관리자 권한으로 실행해야 합니다!

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  WSL2 자동 설치 스크립트" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 관리자 권한 확인
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ 오류: 관리자 권한이 필요합니다!" -ForegroundColor Red
    Write-Host ""
    Write-Host "해결 방법:" -ForegroundColor Yellow
    Write-Host "  1. PowerShell을 우클릭" -ForegroundColor Yellow
    Write-Host "  2. '관리자 권한으로 실행' 선택" -ForegroundColor Yellow
    Write-Host "  3. 이 스크립트 다시 실행" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "아무 키나 눌러 종료"
    exit 1
}

Write-Host "✅ 관리자 권한 확인 완료" -ForegroundColor Green
Write-Host ""

# WSL 설치 여부 확인
Write-Host "📋 WSL 설치 여부 확인 중..." -ForegroundColor Yellow

$wslInstalled = Get-Command wsl -ErrorAction SilentlyContinue

if ($wslInstalled) {
    Write-Host "⚠️  WSL이 이미 설치되어 있습니다!" -ForegroundColor Yellow
    Write-Host ""

    $wslVersion = wsl --list --verbose 2>&1
    Write-Host $wslVersion
    Write-Host ""

    $continue = Read-Host "계속 진행하시겠습니까? (Y/N)"
    if ($continue -ne "Y" -and $continue -ne "y") {
        Write-Host "설치를 취소합니다." -ForegroundColor Yellow
        exit 0
    }
}

# WSL 설치
Write-Host ""
Write-Host "🚀 WSL 설치를 시작합니다..." -ForegroundColor Cyan
Write-Host ""
Write-Host "이 과정은 5-10분 정도 걸립니다." -ForegroundColor Yellow
Write-Host "잠시만 기다려주세요..." -ForegroundColor Yellow
Write-Host ""

try {
    wsl --install

    Write-Host ""
    Write-Host "======================================" -ForegroundColor Green
    Write-Host "  ✅ WSL 설치 완료!" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "🔄 다음 단계:" -ForegroundColor Cyan
    Write-Host "  1. 컴퓨터를 재시작합니다" -ForegroundColor White
    Write-Host "  2. 재시작 후 Ubuntu가 자동으로 실행됩니다" -ForegroundColor White
    Write-Host "  3. 사용자 이름과 비밀번호를 설정합니다" -ForegroundColor White
    Write-Host ""
    Write-Host "💡 팁:" -ForegroundColor Yellow
    Write-Host "  - 사용자 이름: wnstn4647 (권장)" -ForegroundColor White
    Write-Host "  - 비밀번호: 입력해도 화면에 안 보입니다 (정상)" -ForegroundColor White
    Write-Host ""

    $restart = Read-Host "지금 재시작하시겠습니까? (Y/N)"
    if ($restart -eq "Y" -or $restart -eq "y") {
        Write-Host ""
        Write-Host "컴퓨터를 재시작합니다..." -ForegroundColor Cyan
        Start-Sleep -Seconds 3
        Restart-Computer
    } else {
        Write-Host ""
        Write-Host "수동으로 재시작해주세요!" -ForegroundColor Yellow
        Write-Host ""
    }

} catch {
    Write-Host ""
    Write-Host "❌ 오류 발생!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "📖 해결 방법:" -ForegroundColor Yellow
    Write-Host "  1. Windows 업데이트 실행 (설정 → Windows 업데이트)" -ForegroundColor White
    Write-Host "  2. Build 19041 이상 필요 (winver 명령어로 확인)" -ForegroundColor White
    Write-Host "  3. 가상화 기능이 BIOS에서 활성화되어 있는지 확인" -ForegroundColor White
    Write-Host ""
}

Write-Host ""
Read-Host "아무 키나 눌러 종료"
