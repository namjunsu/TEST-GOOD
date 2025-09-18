#!/bin/bash
# 빠른 시작 스크립트

echo "🚀 빠른 시작 모드"
echo "================================"

# 1. 캐시 사전 구축 (백그라운드)
echo "📚 캐시 구축 중... (백그라운드)"
python3 preload_cache.py &
CACHE_PID=$!

# 2. 잠시 대기 (캐시 시작 대기)
sleep 2

# 3. Streamlit 실행
echo "🌐 웹 인터페이스 시작..."
streamlit run web_interface.py

# 캐시 프로세스 정리
kill $CACHE_PID 2>/dev/null