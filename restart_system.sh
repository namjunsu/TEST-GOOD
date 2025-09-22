#!/bin/bash
#
# AI-CHAT RAG 시스템 재시작 스크립트
#

echo "=================================="
echo "🔄 AI-CHAT RAG 시스템 재시작"
echo "=================================="
echo ""

# 1. 기존 시스템 중지
echo "⏹️ 기존 시스템 중지 중..."
./stop_system.sh

# 잠시 대기
sleep 3

# 2. 시스템 시작
echo ""
echo "🚀 시스템 재시작 중..."
./start_system.sh

echo ""
echo "✅ 시스템 재시작 완료!"