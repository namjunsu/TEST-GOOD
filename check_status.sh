#!/bin/bash
#
# AI-CHAT RAG 시스템 상태 확인
#

echo "=================================="
echo "📊 AI-CHAT 시스템 상태"
echo "=================================="
echo ""

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 프로세스 상태
echo "🔍 프로세스 상태:"
echo "-------------------"

# 웹 인터페이스
if pgrep -f "streamlit run web_interface.py" > /dev/null; then
    PID=$(pgrep -f "streamlit run web_interface.py")
    echo -e "${GREEN}✅ 웹 인터페이스: 실행 중 (PID: $PID)${NC}"
else
    echo -e "${RED}❌ 웹 인터페이스: 중지됨${NC}"
fi

# 자동 인덱싱
if pgrep -f "auto_indexer.py" > /dev/null; then
    PID=$(pgrep -f "auto_indexer.py")
    echo -e "${GREEN}✅ 자동 인덱싱: 실행 중 (PID: $PID)${NC}"
else
    echo -e "${RED}❌ 자동 인덱싱: 중지됨${NC}"
fi

# OCR 모니터
if pgrep -f "auto_ocr_monitor.py" > /dev/null; then
    PID=$(pgrep -f "auto_ocr_monitor.py")
    echo -e "${GREEN}✅ OCR 모니터: 실행 중 (PID: $PID)${NC}"
else
    echo -e "${RED}❌ OCR 모니터: 중지됨${NC}"
fi

echo ""

# 2. 문서 통계
echo "📚 문서 통계:"
echo "-------------------"
TOTAL_PDF=$(find docs -name "*.pdf" | wc -l)
UNIQUE_PDF=$(find docs -name "*.pdf" -exec basename {} \; | sort | uniq | wc -l)
echo "총 PDF 파일: $TOTAL_PDF개"
echo "고유 문서: $UNIQUE_PDF개"

if [ -f document_metadata.json ]; then
    METADATA_COUNT=$(grep -c '"filename"' document_metadata.json 2>/dev/null || echo 0)
    echo "메타데이터 저장: $METADATA_COUNT개"
fi

echo ""

# 3. 디스크 사용량
echo "💾 디스크 사용량:"
echo "-------------------"
DOCS_SIZE=$(du -sh docs 2>/dev/null | cut -f1)
echo "문서 폴더: $DOCS_SIZE"

if [ -d logs ]; then
    LOGS_SIZE=$(du -sh logs 2>/dev/null | cut -f1)
    echo "로그 폴더: $LOGS_SIZE"
fi

echo ""

# 4. 최근 활동
echo "📝 최근 활동:"
echo "-------------------"

# 최근 추가된 문서
RECENT_DOCS=$(find docs -name "*.pdf" -mtime -1 | wc -l)
if [ $RECENT_DOCS -gt 0 ]; then
    echo -e "${YELLOW}• 24시간 내 추가된 문서: $RECENT_DOCS개${NC}"
fi

# 최근 로그
if [ -f logs/web_interface.log ]; then
    LAST_LOG=$(tail -1 logs/web_interface.log 2>/dev/null | cut -c1-50)
    echo "• 최근 웹 로그: $LAST_LOG..."
fi

echo ""

# 5. 시스템 리소스
echo "⚙️ 시스템 리소스:"
echo "-------------------"
# 메모리 사용률
MEM_USAGE=$(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2}')
echo "메모리 사용률: $MEM_USAGE"

# GPU 상태 (있는 경우)
if command -v nvidia-smi &> /dev/null; then
    GPU_USAGE=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ ! -z "$GPU_USAGE" ]; then
        echo "GPU 사용률: $GPU_USAGE%"
    fi
fi

echo ""
echo "=================================="
echo ""
echo "🔧 관리 명령어:"
echo "  시작: ./start_system.sh"
echo "  중지: ./stop_system.sh"
echo "  재시작: ./restart_system.sh"
echo ""