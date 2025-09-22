#!/bin/bash
#
# AI-CHAT 시스템 백업 스크립트
#

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================="
echo "💾 AI-CHAT 시스템 백업"
echo "=================================="
echo ""

# 백업 디렉토리 설정
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

echo "📁 백업 디렉토리: $BACKUP_DIR"
echo ""

# 1. 메타데이터 백업
echo "1️⃣ 메타데이터 백업 중..."
if [ -f document_metadata.json ]; then
    cp document_metadata.json $BACKUP_DIR/
    echo -e "${GREEN}✅ document_metadata.json${NC}"
fi

if [ -f metadata.db ]; then
    cp metadata.db $BACKUP_DIR/
    echo -e "${GREEN}✅ metadata.db${NC}"
fi

# 2. 검색 인덱스 백업
echo ""
echo "2️⃣ 검색 인덱스 백업 중..."
if [ -d rag_system/indexes ]; then
    cp -r rag_system/indexes $BACKUP_DIR/
    echo -e "${GREEN}✅ 검색 인덱스${NC}"
fi

# 3. 설정 파일 백업
echo ""
echo "3️⃣ 설정 파일 백업 중..."
cp config.py $BACKUP_DIR/ 2>/dev/null
cp .env $BACKUP_DIR/ 2>/dev/null
cp -r .streamlit $BACKUP_DIR/ 2>/dev/null
echo -e "${GREEN}✅ 설정 파일${NC}"

# 4. 스크립트 백업
echo ""
echo "4️⃣ 시스템 스크립트 백업 중..."
cp *.sh $BACKUP_DIR/ 2>/dev/null
echo -e "${GREEN}✅ 실행 스크립트${NC}"

# 5. 로그 백업 (최근 7일)
echo ""
echo "5️⃣ 로그 파일 백업 중..."
mkdir -p $BACKUP_DIR/logs
find logs -name "*.log" -mtime -7 -exec cp {} $BACKUP_DIR/logs/ \; 2>/dev/null
echo -e "${GREEN}✅ 최근 로그${NC}"

# 6. 백업 압축
echo ""
echo "📦 백업 압축 중..."
tar -czf "$BACKUP_DIR.tar.gz" -C backups $(basename $BACKUP_DIR)
rm -rf $BACKUP_DIR

# 7. 오래된 백업 정리 (30일 이상)
echo ""
echo "🧹 오래된 백업 정리 중..."
find backups -name "*.tar.gz" -mtime +30 -delete 2>/dev/null

# 8. 백업 통계
BACKUP_SIZE=$(du -h "$BACKUP_DIR.tar.gz" | cut -f1)
BACKUP_COUNT=$(find backups -name "*.tar.gz" | wc -l)

echo ""
echo "=================================="
echo -e "${GREEN}✅ 백업 완료!${NC}"
echo "=================================="
echo "📊 백업 정보:"
echo "   • 백업 파일: $(basename $BACKUP_DIR.tar.gz)"
echo "   • 백업 크기: $BACKUP_SIZE"
echo "   • 총 백업 개수: $BACKUP_COUNT개"
echo ""
echo "💡 복원 방법:"
echo "   ./restore_backup.sh $BACKUP_DIR.tar.gz"
echo ""