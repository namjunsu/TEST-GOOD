#!/bin/bash
#
# AI-CHAT RAG 시스템 재시작 스크립트 (Docker 버전)
#

echo "=================================="
echo "🔄 AI-CHAT RAG 시스템 재시작 (Docker)"
echo "=================================="
echo ""

# Docker Compose로 시스템 재시작
echo "🐳 Docker 컨테이너 재시작 중..."
docker compose restart

# 상태 확인
echo ""
echo "📊 시스템 상태 확인:"
docker compose ps

echo ""
echo "✅ 시스템 재시작 완료!"
echo ""
echo "🌐 웹 인터페이스: http://localhost:8501"
echo "📊 Grafana: http://localhost:3000"
echo "📈 Prometheus: http://localhost:9090"