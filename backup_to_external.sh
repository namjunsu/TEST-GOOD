#!/bin/bash
# AI-CHAT 전체 백업 스크립트 (외장하드용)
# 사용법: sudo ./backup_to_external.sh

set -e

echo "=========================================="
echo "AI-CHAT 외장하드 백업 스크립트"
echo "=========================================="
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 현재 디렉토리
SOURCE_DIR="/home/user/Desktop/AI/AI-CHAT"
EXTERNAL_DEVICE="/dev/sdb1"
MOUNT_POINT="/media/user/external_backup"

# 1. 외장하드 마운트 확인
echo -e "${YELLOW}[1/4] 외장하드 확인 중...${NC}"
if mount | grep -q "$EXTERNAL_DEVICE"; then
    CURRENT_MOUNT=$(mount | grep "$EXTERNAL_DEVICE" | awk '{print $3}')
    echo -e "${GREEN}✓ 외장하드가 이미 마운트되어 있습니다: $CURRENT_MOUNT${NC}"
    MOUNT_POINT="$CURRENT_MOUNT"
else
    echo "외장하드를 마운트합니다..."
    mkdir -p "$MOUNT_POINT"

    # NTFS 드라이브 마운트 (ntfs-3g 사용)
    if mount -t ntfs-3g "$EXTERNAL_DEVICE" "$MOUNT_POINT" -o uid=$(id -u user),gid=$(id -g user),umask=022; then
        echo -e "${GREEN}✓ 외장하드 마운트 완료: $MOUNT_POINT${NC}"
    else
        echo -e "${RED}✗ 외장하드 마운트 실패!${NC}"
        echo "다음 명령어로 수동 마운트를 시도하세요:"
        echo "  sudo mount -t ntfs-3g $EXTERNAL_DEVICE $MOUNT_POINT"
        exit 1
    fi
fi

# 2. 공간 확인
echo ""
echo -e "${YELLOW}[2/4] 디스크 공간 확인 중...${NC}"
SOURCE_SIZE=$(du -sb "$SOURCE_DIR" | awk '{print $1}')
SOURCE_SIZE_GB=$(echo "scale=2; $SOURCE_SIZE / 1024 / 1024 / 1024" | bc)
AVAILABLE_SPACE=$(df "$MOUNT_POINT" | tail -1 | awk '{print $4}')
AVAILABLE_SPACE_GB=$(echo "scale=2; $AVAILABLE_SPACE / 1024 / 1024" | bc)

echo "원본 크기: ${SOURCE_SIZE_GB} GB"
echo "외장하드 여유 공간: ${AVAILABLE_SPACE_GB} GB"

if [ "$AVAILABLE_SPACE" -lt "$SOURCE_SIZE" ]; then
    echo -e "${RED}✗ 외장하드 공간이 부족합니다!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 공간 충분${NC}"

# 3. 백업 실행
BACKUP_DIR="$MOUNT_POINT/AI-CHAT-backup-$(date +%Y%m%d-%H%M%S)"
echo ""
echo -e "${YELLOW}[3/4] 백업 시작...${NC}"
echo "대상 경로: $BACKUP_DIR"
echo ""
echo "복사 중... (40GB+ 예상, 수 분 소요)"

# rsync로 전체 복사 (진행률 표시)
rsync -ah --info=progress2 \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='logs/*.log' \
    --exclude='.git/objects/' \
    "$SOURCE_DIR/" "$BACKUP_DIR/"

echo ""
echo -e "${GREEN}✓ 파일 복사 완료${NC}"

# 4. 검증
echo ""
echo -e "${YELLOW}[4/4] 백업 검증 중...${NC}"

# 주요 디렉토리 확인
CRITICAL_DIRS=("models" "app" "components" "config" "scripts" "rag_system" "docs" "var")
ALL_OK=true

for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$BACKUP_DIR/$dir" ]; then
        echo -e "${GREEN}✓${NC} $dir/"
    else
        echo -e "${RED}✗${NC} $dir/ (누락!)"
        ALL_OK=false
    fi
done

# 주요 파일 확인
CRITICAL_FILES=("requirements.txt" "start_ai_chat.sh" ".env" "README.md")
for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$BACKUP_DIR/$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${YELLOW}⚠${NC} $file (선택적)"
    fi
done

# 최종 결과
echo ""
echo "=========================================="
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}백업 완료!${NC}"
    echo ""
    echo "백업 위치: $BACKUP_DIR"
    echo "백업 크기: $(du -sh "$BACKUP_DIR" | awk '{print $1}')"
    echo ""
    echo -e "${YELLOW}새 PC에서 복원 방법:${NC}"
    echo "1. 외장하드를 새 PC에 연결"
    echo "2. cp -r '$BACKUP_DIR' ~/Desktop/AI/AI-CHAT"
    echo "3. cd ~/Desktop/AI/AI-CHAT"
    echo "4. python3 -m venv .venv"
    echo "5. source .venv/bin/activate"
    echo "6. pip install -r requirements.txt"
    echo "7. nano .env  # 경로 수정"
    echo "8. ./start_ai_chat.sh"
else
    echo -e "${RED}백업 중 일부 파일이 누락되었습니다!${NC}"
    echo "백업을 다시 확인해주세요."
fi
echo "=========================================="
