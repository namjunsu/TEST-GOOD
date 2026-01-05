#!/bin/bash
# AI-CHAT 외장하드 백업 스크립트 (간단 버전)
# 실행: sudo bash backup_simple.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "AI-CHAT 외장하드 백업"
echo "=========================================="
echo ""

# 외장하드가 root로 마운트되어 있으면 언마운트 후 재마운트
if mount | grep -q "/dev/sdb1"; then
    CURRENT_MOUNT=$(mount | grep "/dev/sdb1" | awk '{print $3}')
    echo -e "${YELLOW}외장하드가 $CURRENT_MOUNT 에 마운트되어 있습니다.${NC}"

    # root 소유인지 확인
    if [[ "$CURRENT_MOUNT" == "/media/root/"* ]]; then
        echo "사용자 권한으로 재마운트합니다..."
        umount /dev/sdb1
        sleep 1
    else
        echo -e "${GREEN}✓ 이미 사용자 권한으로 마운트됨${NC}"
        BACKUP_ROOT="$CURRENT_MOUNT"
    fi
fi

# 사용자 권한으로 마운트
if ! mount | grep -q "/dev/sdb1"; then
    BACKUP_ROOT="/media/$USER/external_backup"
    mkdir -p "$BACKUP_ROOT"
    mount -t ntfs-3g /dev/sdb1 "$BACKUP_ROOT" -o uid=$(id -u $USER),gid=$(id -g $USER),umask=022
    echo -e "${GREEN}✓ 외장하드 마운트 완료: $BACKUP_ROOT${NC}"
else
    BACKUP_ROOT=$(mount | grep "/dev/sdb1" | awk '{print $3}')
fi

echo ""

# 공간 확인
SOURCE_DIR="/home/user/Desktop/AI/AI-CHAT"
echo -e "${YELLOW}디스크 공간 확인 중...${NC}"
SOURCE_SIZE=$(du -sb "$SOURCE_DIR" 2>/dev/null | awk '{print $1}')
SOURCE_SIZE_GB=$(echo "scale=1; $SOURCE_SIZE / 1024 / 1024 / 1024" | bc)
# df는 1K 블록 단위로 출력, 바이트로 변환 (* 1024)
AVAILABLE_KB=$(df "$BACKUP_ROOT" | tail -1 | awk '{print $4}')
AVAILABLE_BYTES=$(echo "$AVAILABLE_KB * 1024" | bc)
AVAILABLE_GB=$(echo "scale=1; $AVAILABLE_BYTES / 1024 / 1024 / 1024" | bc)

echo "원본 크기: ${SOURCE_SIZE_GB} GB"
echo "외장하드 여유 공간: ${AVAILABLE_GB} GB"

# 바이트 단위로 비교
if [ "$AVAILABLE_BYTES" -lt "$SOURCE_SIZE" ]; then
    echo -e "${RED}✗ 외장하드 공간이 부족합니다!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 공간 충분${NC}"
echo ""

# 백업 디렉토리 생성
BACKUP_DIR="$BACKUP_ROOT/AI-CHAT-backup-$(date +%Y%m%d-%H%M%S)"
echo -e "${YELLOW}백업 시작...${NC}"
echo "대상: $BACKUP_DIR"
echo ""
echo "복사 중... (예상 시간: 5~10분)"
echo ""

# rsync로 복사 (진행률 표시)
rsync -ah --info=progress2 \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='htmlcov/' \
    --exclude='.git/objects/pack/*.pack' \
    "$SOURCE_DIR/" "$BACKUP_DIR/"

echo ""
echo -e "${GREEN}✓ 복사 완료!${NC}"
echo ""

# 검증
echo -e "${YELLOW}백업 검증 중...${NC}"
CRITICAL_DIRS=("models" "app" "components" "config" "scripts" "rag_system" "docs" "var")
ALL_OK=true

for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$BACKUP_DIR/$dir" ]; then
        SIZE=$(du -sh "$BACKUP_DIR/$dir" 2>/dev/null | awk '{print $1}')
        echo -e "${GREEN}✓${NC} $dir/ ($SIZE)"
    else
        echo -e "${RED}✗${NC} $dir/ (누락!)"
        ALL_OK=false
    fi
done

# 주요 파일
echo ""
CRITICAL_FILES=("INSTALL_NEW_PC.sh" "requirements.txt" "start_ai_chat.sh" ".env" "새PC설치가이드.md")
for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$BACKUP_DIR/$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${YELLOW}⚠${NC} $file"
    fi
done

echo ""
echo "=========================================="
if [ "$ALL_OK" = true ]; then
    BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}백업 완료! ✅${NC}"
    echo ""
    echo "📦 백업 위치: $BACKUP_DIR"
    echo "📊 백업 크기: $BACKUP_SIZE"
    echo ""
    echo -e "${YELLOW}새 PC에서 복원 방법:${NC}"
    echo ""
    echo "1. 외장하드를 새 PC에 연결"
    echo ""
    echo "2. 백업 복사:"
    echo "   cp -r '$BACKUP_DIR' ~/Desktop/AI-CHAT"
    echo ""
    echo "3. 자동 설치:"
    echo "   cd ~/Desktop/AI-CHAT"
    echo "   ./INSTALL_NEW_PC.sh"
    echo ""
    echo "4. 실행:"
    echo "   source .venv/bin/activate"
    echo "   ./start_ai_chat.sh"
    echo ""
    echo "자세한 내용은 '새PC설치가이드.md' 파일을 참고하세요!"
else
    echo -e "${RED}⚠ 백업 중 일부 파일이 누락되었습니다!${NC}"
fi
echo "=========================================="
