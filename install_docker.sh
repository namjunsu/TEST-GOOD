#!/bin/bash

# Docker 설치 스크립트 for Ubuntu/WSL2
# 사용법: bash install_docker.sh

set -e

echo "🐳 Docker 설치를 시작합니다..."

# 1. 기존 Docker 제거 (있는 경우)
echo "📦 기존 Docker 제거 중..."
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# 2. 필수 패키지 설치
echo "📦 필수 패키지 설치 중..."
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 3. Docker 공식 GPG 키 추가
echo "🔑 Docker GPG 키 추가 중..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 4. Docker 저장소 추가
echo "📋 Docker 저장소 추가 중..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Docker 설치
echo "🐳 Docker 설치 중..."
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. 현재 사용자를 docker 그룹에 추가
echo "👤 사용자를 docker 그룹에 추가 중..."
sudo usermod -aG docker $USER

# 7. Docker 서비스 시작
echo "🚀 Docker 서비스 시작 중..."
sudo service docker start

# 8. 설치 확인
echo ""
echo "✅ Docker 설치 완료!"
echo ""
echo "📋 설치된 버전:"
docker --version
docker compose version

echo ""
echo "⚠️  중요: 다음 명령어를 실행하여 그룹 변경사항을 적용하세요:"
echo "   newgrp docker"
echo ""
echo "또는 터미널을 재시작하세요."
echo ""
echo "🐳 Docker 사용 준비 완료!"
echo ""
echo "다음 명령어로 AI-CHAT을 실행하세요:"
echo "   cd /home/wnstn4647/AI-CHAT"
echo "   docker compose up -d"
