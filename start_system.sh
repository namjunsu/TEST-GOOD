#!/bin/bash
#
# AI-CHAT RAG 시스템 자동 시작 스크립트
# 누구나 이 스크립트만 실행하면 전체 시스템이 작동합니다
#

echo "=================================="
echo "🚀 AI-CHAT RAG 시스템 시작"
echo "=================================="

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 로그 디렉토리 생성
mkdir -p logs

# 1. 기존 프로세스 정리
echo "🔧 기존 프로세스 정리 중..."
pkill -f streamlit 2>/dev/null
pkill -f auto_indexer 2>/dev/null
pkill -f auto_ocr_monitor 2>/dev/null
sleep 2

# 2. 웹 인터페이스 시작
echo "🌐 웹 인터페이스 시작 중..."
nohup streamlit run web_interface.py > logs/web_interface.log 2>&1 &
WEB_PID=$!
sleep 3

# 3. 자동 인덱싱 시작
echo "📚 자동 인덱싱 시작 중..."
nohup python3 auto_indexer.py > logs/auto_indexer.log 2>&1 &
INDEX_PID=$!
sleep 2

# 4. OCR 모니터 시작
echo "🔍 OCR 자동 처리 시작 중..."
nohup python3 auto_ocr_monitor.py > logs/ocr_monitor.log 2>&1 &
OCR_PID=$!
sleep 2

# 5. 상태 확인
echo ""
echo "📊 시스템 상태 확인 중..."
sleep 2

# 프로세스 확인
if ps -p $WEB_PID > /dev/null; then
    echo -e "${GREEN}✅ 웹 인터페이스: 실행 중 (PID: $WEB_PID)${NC}"
else
    echo -e "${RED}❌ 웹 인터페이스: 실행 실패${NC}"
fi

if ps -p $INDEX_PID > /dev/null; then
    echo -e "${GREEN}✅ 자동 인덱싱: 실행 중 (PID: $INDEX_PID)${NC}"
else
    echo -e "${RED}❌ 자동 인덱싱: 실행 실패${NC}"
fi

if ps -p $OCR_PID > /dev/null; then
    echo -e "${GREEN}✅ OCR 모니터: 실행 중 (PID: $OCR_PID)${NC}"
else
    echo -e "${RED}❌ OCR 모니터: 실행 실패${NC}"
fi

# PID 저장
echo $WEB_PID > logs/web.pid
echo $INDEX_PID > logs/indexer.pid
echo $OCR_PID > logs/ocr.pid

echo ""
echo "=================================="
echo "🎉 시스템 시작 완료!"
echo "=================================="
echo ""
echo "📌 웹 인터페이스 접속:"
echo "   http://localhost:8501"
echo ""
echo "📌 로그 확인:"
echo "   tail -f logs/web_interface.log"
echo ""
echo "📌 시스템 중지:"
echo "   ./stop_system.sh"
echo ""