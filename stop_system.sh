#!/bin/bash
#
# AI-CHAT RAG 시스템 중지 스크립트
#

echo "=================================="
echo "🛑 AI-CHAT RAG 시스템 중지"
echo "=================================="

# PID 파일에서 프로세스 ID 읽기
if [ -f logs/web.pid ]; then
    WEB_PID=$(cat logs/web.pid)
    if ps -p $WEB_PID > /dev/null 2>&1; then
        kill $WEB_PID
        echo "✅ 웹 인터페이스 중지됨"
    fi
    rm logs/web.pid
fi

if [ -f logs/indexer.pid ]; then
    INDEX_PID=$(cat logs/indexer.pid)
    if ps -p $INDEX_PID > /dev/null 2>&1; then
        kill $INDEX_PID
        echo "✅ 자동 인덱싱 중지됨"
    fi
    rm logs/indexer.pid
fi

if [ -f logs/ocr.pid ]; then
    OCR_PID=$(cat logs/ocr.pid)
    if ps -p $OCR_PID > /dev/null 2>&1; then
        kill $OCR_PID
        echo "✅ OCR 모니터 중지됨"
    fi
    rm logs/ocr.pid
fi

# 혹시 남은 프로세스 정리
pkill -f streamlit 2>/dev/null
pkill -f auto_indexer 2>/dev/null
pkill -f auto_ocr_monitor 2>/dev/null

echo ""
echo "✅ 모든 프로세스가 중지되었습니다."
echo ""