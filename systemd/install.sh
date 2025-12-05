#!/bin/bash
# AI-CHAT systemd 서비스 설치 스크립트
# 사용법: sudo ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="/etc/systemd/system"

echo "=== AI-CHAT systemd 서비스 설치 ==="

# 1. 서비스 파일 복사
echo "[1/4] 서비스 파일 복사..."
sudo cp "$SCRIPT_DIR/ai-chat-api.service" "$SERVICE_DIR/"
sudo cp "$SCRIPT_DIR/ai-chat-web.service" "$SERVICE_DIR/"

# 2. 로그 디렉토리 생성
echo "[2/4] 로그 디렉토리 생성..."
mkdir -p /home/wnstn4647/AI-CHAT/logs

# 3. systemd 리로드
echo "[3/4] systemd 데몬 리로드..."
sudo systemctl daemon-reload

# 4. 서비스 활성화
echo "[4/4] 서비스 활성화..."
sudo systemctl enable ai-chat-api.service
sudo systemctl enable ai-chat-web.service

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "사용법:"
echo "  시작:   sudo systemctl start ai-chat-api ai-chat-web"
echo "  중지:   sudo systemctl stop ai-chat-api ai-chat-web"
echo "  상태:   sudo systemctl status ai-chat-api ai-chat-web"
echo "  로그:   journalctl -u ai-chat-api -f"
echo ""
echo "부팅 시 자동 시작이 활성화되었습니다."
