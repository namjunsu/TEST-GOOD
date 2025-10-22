#!/bin/bash
# 프로젝트 복사 및 설치 스크립트
# Ubuntu 터미널에서 실행: bash 3_프로젝트_설치.sh

set -e  # 오류 발생시 중단

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}======================================"
echo "  프로젝트 복사 및 설치 스크립트"
echo "======================================${NC}"
echo ""

# Step 1: Windows 경로 확인
echo -e "${CYAN}📋 Step 1: Windows 프로젝트 폴더 확인${NC}"
echo "─────────────────────────────────"

WINDOWS_PATH="/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT"

if [ -d "$WINDOWS_PATH" ]; then
    echo -e "${GREEN}✅ Windows 프로젝트 폴더 발견!${NC}"
    echo "   경로: $WINDOWS_PATH"

    # 폴더 크기 확인
    FOLDER_SIZE=$(du -sh "$WINDOWS_PATH" 2>/dev/null | cut -f1)
    echo "   크기: $FOLDER_SIZE"

    # PDF 개수 확인
    PDF_COUNT=$(find "$WINDOWS_PATH/docs" -name "*.pdf" 2>/dev/null | wc -l)
    echo "   PDF 문서: ${PDF_COUNT}개"
else
    echo -e "${RED}❌ Windows 프로젝트 폴더를 찾을 수 없습니다!${NC}"
    echo ""
    echo "경로를 확인해주세요:"
    echo "  Windows: C:\\Users\\wnstn\\OneDrive\\Desktop\\AI\\AI-CHAT"
    echo "  WSL: /mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT"
    echo ""
    exit 1
fi

echo ""

# Step 2: 기존 폴더 확인
echo -e "${CYAN}📋 Step 2: 기존 폴더 확인${NC}"
echo "─────────────────────────────────"

TARGET_PATH="$HOME/AI-CHAT"

if [ -d "$TARGET_PATH" ]; then
    echo -e "${YELLOW}⚠️  ~/AI-CHAT 폴더가 이미 존재합니다${NC}"
    echo ""
    read -p "삭제하고 새로 복사하시겠습니까? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "기존 폴더를 삭제합니다..."
        rm -rf "$TARGET_PATH"
        echo -e "${GREEN}✅ 삭제 완료${NC}"
    else
        echo -e "${YELLOW}기존 폴더를 유지합니다${NC}"
        echo "설치를 건너뜁니다."
        echo ""
        echo "SETUP_NEW_PC.sh를 실행하려면:"
        echo "  cd ~/AI-CHAT"
        echo "  bash SETUP_NEW_PC.sh"
        exit 0
    fi
fi

echo ""

# Step 3: 프로젝트 복사
echo -e "${CYAN}📋 Step 3: 프로젝트 복사 (시간이 걸릴 수 있습니다)${NC}"
echo "─────────────────────────────────"
echo "복사 중..."
echo ""

# 복사 시작 시간 기록
START_TIME=$(date +%s)

# 복사 진행
cp -r "$WINDOWS_PATH" "$TARGET_PATH"

# 복사 완료 시간 계산
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo -e "${GREEN}✅ 프로젝트 복사 완료 (소요 시간: ${ELAPSED}초)${NC}"
echo ""

# Step 4: 권한 설정
echo -e "${CYAN}📋 Step 4: 권한 설정${NC}"
echo "─────────────────────────────────"

cd "$TARGET_PATH"

# 스크립트 실행 권한
chmod +x *.sh 2>/dev/null || true

# 소유권 설정
sudo chown -R $USER:$USER "$TARGET_PATH"

echo -e "${GREEN}✅ 권한 설정 완료${NC}"
echo ""

# Step 5: 복사 결과 확인
echo -e "${CYAN}📋 Step 5: 복사 결과 확인${NC}"
echo "─────────────────────────────────"

if [ -f "$TARGET_PATH/web_interface.py" ]; then
    echo -e "${GREEN}✅${NC} web_interface.py"
else
    echo -e "${RED}❌${NC} web_interface.py"
fi

if [ -f "$TARGET_PATH/SETUP_NEW_PC.sh" ]; then
    echo -e "${GREEN}✅${NC} SETUP_NEW_PC.sh"
else
    echo -e "${RED}❌${NC} SETUP_NEW_PC.sh"
fi

if [ -f "$TARGET_PATH/requirements.txt" ]; then
    echo -e "${GREEN}✅${NC} requirements.txt"
else
    echo -e "${RED}❌${NC} requirements.txt"
fi

if [ -d "$TARGET_PATH/docs" ]; then
    PDF_COUNT_NEW=$(find "$TARGET_PATH/docs" -name "*.pdf" 2>/dev/null | wc -l)
    echo -e "${GREEN}✅${NC} docs/ 폴더 (PDF: ${PDF_COUNT_NEW}개)"
else
    echo -e "${RED}❌${NC} docs/ 폴더"
fi

echo ""

# Step 6: 자동 설치 실행 여부 확인
echo -e "${CYAN}======================================${NC}"
echo -e "${GREEN}  ✅ 프로젝트 복사 완료!${NC}"
echo -e "${CYAN}======================================${NC}"
echo ""
echo -e "${CYAN}🎯 다음 단계:${NC}"
echo ""
echo "  자동 설치 스크립트를 실행하시겠습니까?"
echo "  (Python 가상환경 생성 및 패키지 설치 - 약 10분 소요)"
echo ""

read -p "자동 설치를 시작하시겠습니까? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${CYAN}자동 설치를 시작합니다...${NC}"
    echo ""
    sleep 2

    cd "$TARGET_PATH"
    bash SETUP_NEW_PC.sh
else
    echo ""
    echo -e "${YELLOW}나중에 수동으로 실행하세요:${NC}"
    echo ""
    echo "  cd ~/AI-CHAT"
    echo "  bash SETUP_NEW_PC.sh"
    echo ""
fi
