#!/bin/bash
# 빠른 시작 스크립트

echo "⚡ AI-CHAT 빠른 시작 모드"
echo "========================="

# 환경 변수 설정 (제한 모드)
export MAX_DOCUMENTS=50
export USE_CACHE=true
export LOW_VRAM=true
export LOG_LEVEL=WARNING

# 캐시 확인
if [ -d ".cache" ]; then
    echo "✅ 캐시 발견 - 빠른 로딩 가능"
else
    echo "⚠️  캐시 없음 - 초기 구축 필요"
    python3 fast_startup_optimizer.py --build-cache
fi

# Streamlit 실행
echo ""
echo "🚀 웹 인터페이스 시작..."
streamlit run web_interface.py

