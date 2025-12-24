#!/bin/bash
# GPU/시스템 실시간 모니터링
# 사용법: ./scripts/monitor.sh

# 초기 CPU 통계 읽기
get_cpu_usage() {
    # /proc/stat 사용 - 간단하고 빠름
    awk '/^cpu / {usage=($2+$4)*100/($2+$4+$5)} END {printf "%.1f", usage}' /proc/stat
}

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

    # CPU 사용률 (간격 측정)
    cpu_before=$(cat /proc/stat | grep '^cpu ')
    sleep 0.5
    cpu_after=$(cat /proc/stat | grep '^cpu ')

    read -r _ user1 nice1 sys1 idle1 _ <<< "$cpu_before"
    read -r _ user2 nice2 sys2 idle2 _ <<< "$cpu_after"

    total1=$((user1 + nice1 + sys1 + idle1))
    total2=$((user2 + nice2 + sys2 + idle2))
    idle_delta=$((idle2 - idle1))
    total_delta=$((total2 - total1))

    if [ $total_delta -gt 0 ]; then
        cpu_pct=$(awk "BEGIN {printf \"%.1f\", 100.0 * (1 - $idle_delta / $total_delta)}")
    else
        cpu_pct="0.0"
    fi

    echo "  CPU:  ${cpu_pct}%"

    # RAM 사용량
    free -h | awk '/Mem:/ {printf "  RAM:  %s / %s (%.1f%%)\n", $3, $2, $3/$2*100}'

    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  Ctrl+C 종료"

    sleep 0.5
done
