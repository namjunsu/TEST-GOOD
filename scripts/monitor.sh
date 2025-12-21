#!/bin/bash
# GPU/시스템 실시간 모니터링
# 사용법: ./scripts/monitor.sh

while true; do
    clear
    echo "═══════════════════════════════════════════════"
    echo "  AI-CHAT 시스템 모니터  $(date '+%H:%M:%S')"
    echo "═══════════════════════════════════════════════"
    echo ""

    # GPU 정보
    nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader | \
        awk -F", " '{printf "  GPU:  %s\n  사용: %s | 메모리: %s / %s | 온도: %s°C\n", $1, $2, $3, $4, $5}'
    echo ""

    # CPU 사용률
    CPU=$(grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {printf "%.1f", usage}')
    echo "  CPU:  ${CPU}%"

    # RAM 사용량
    free -h | awk '/Mem:/ {printf "  RAM:  %s / %s (%.1f%%)\n", $3, $2, $3/$2*100}'

    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  Ctrl+C 종료"

    sleep 1
done
