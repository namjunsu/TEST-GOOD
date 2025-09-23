#!/bin/bash
#
# AI-CHAT RAG 시스템 자동 시작 스크립트 (Docker 버전)
# 누구나 이 스크립트만 실행하면 전체 시스템이 작동합니다
#

echo "=================================="
echo "🚀 AI-CHAT RAG 시스템 시작 (Docker)"
echo "=================================="

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Docker Compose로 시스템 시작
echo "🐳 Docker 컨테이너 시작 중..."
docker compose up -d

# 잠시 대기
sleep 5

# 상태 확인
echo ""
echo "📊 시스템 상태 확인:"
docker compose ps

echo ""
echo "=================================="
echo "🎉 시스템 시작 완료!"
echo "=================================="
echo ""
echo "📌 웹 인터페이스 접속:"
echo "   🌐 http://localhost:8501"
echo ""
echo "📌 모니터링 대시보드:"
echo "   📊 Grafana: http://localhost:3000"
echo "   📈 Prometheus: http://localhost:9090"
echo ""
echo "📌 로그 확인:"
echo "   docker compose logs -f rag-system"
echo ""
echo "📌 시스템 중지:"
echo "   docker compose down"
echo ""