#!/bin/bash

echo "🛑 모든 Streamlit 프로세스 종료 중..."

# Kill all streamlit processes
pkill -9 -f streamlit

# Kill any processes on port 8501
lsof -ti:8501 2>/dev/null | xargs -r kill -9

# Wait a moment
sleep 1

# Check if anything is still running
if pgrep -f streamlit > /dev/null; then
    echo "⚠️ 일부 프로세스가 아직 실행 중입니다. 강제 종료..."
    pkill -9 -f streamlit
else
    echo "✅ 모든 프로세스가 종료되었습니다!"
fi

echo ""
echo "📌 시스템 시작 방법:"
echo "   streamlit run web_interface.py"
echo ""
echo "📌 시스템 종료 방법:"
echo "   Ctrl+C 또는 ./stop_all.sh"