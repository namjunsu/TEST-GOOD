#!/bin/bash
#
# AI-CHAT 시스템 복원 스크립트
#

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================="
echo "🔄 AI-CHAT 시스템 복원"
echo "=================================="
echo ""

# 백업 파일 확인
if [ $# -eq 0 ]; then
    echo "사용법: ./restore_backup.sh [백업파일.tar.gz]"
    echo ""
    echo "사용 가능한 백업:"
    ls -lh backups/*.tar.gz 2>/dev/null | awk '{print "  •", $NF, "("$5")"}'
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}❌ 백업 파일을 찾을 수 없습니다: $BACKUP_FILE${NC}"
    exit 1
fi

echo "📦 백업 파일: $BACKUP_FILE"
echo ""
echo -e "${YELLOW}⚠️ 경고: 현재 데이터가 백업 데이터로 대체됩니다!${NC}"
echo "계속하시겠습니까? (y/N)"
read -r CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "복원 취소됨"
    exit 0
fi

# 임시 디렉토리에 압축 해제
TEMP_DIR="/tmp/ai_chat_restore_$(date +%s)"
mkdir -p $TEMP_DIR

echo ""
echo "📂 백업 압축 해제 중..."
tar -xzf $BACKUP_FILE -C $TEMP_DIR

# 압축 해제된 디렉토리 찾기
RESTORE_DIR=$(find $TEMP_DIR -maxdepth 1 -type d | tail -1)

# 1. 시스템 중지
echo ""
echo "⏹️ 시스템 중지 중..."
./stop_system.sh

sleep 2

# 2. 메타데이터 복원
echo ""
echo "1️⃣ 메타데이터 복원 중..."
if [ -f "$RESTORE_DIR/document_metadata.json" ]; then
    cp "$RESTORE_DIR/document_metadata.json" ./
    echo -e "${GREEN}✅ document_metadata.json${NC}"
fi

if [ -f "$RESTORE_DIR/metadata.db" ]; then
    cp "$RESTORE_DIR/metadata.db" ./
    echo -e "${GREEN}✅ metadata.db${NC}"
fi

# 3. 검색 인덱스 복원
echo ""
echo "2️⃣ 검색 인덱스 복원 중..."
if [ -d "$RESTORE_DIR/indexes" ]; then
    rm -rf rag_system/indexes
    cp -r "$RESTORE_DIR/indexes" rag_system/
    echo -e "${GREEN}✅ 검색 인덱스${NC}"
fi

# 4. 설정 파일 복원 (선택적)
echo ""
echo "3️⃣ 설정 파일 복원을 건너뜁니다 (안전을 위해)"

# 5. 정리
rm -rf $TEMP_DIR

echo ""
echo "=================================="
echo -e "${GREEN}✅ 복원 완료!${NC}"
echo "=================================="
echo ""
echo "🚀 시스템 재시작 중..."
./start_system.sh

echo ""
echo "💡 복원된 데이터:"
echo "   • 메타데이터"
echo "   • 검색 인덱스"
echo ""
echo "📌 설정 파일은 수동으로 복원하세요 (필요시)"
echo ""