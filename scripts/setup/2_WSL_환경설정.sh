#!/bin/bash
# WSL 환경 설정 스크립트
# Ubuntu 터미널에서 실행: bash 2_WSL_환경설정.sh

set -e  # 오류 발생시 중단

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}======================================"
echo "  WSL 환경 자동 설정 스크립트"
echo "======================================${NC}"
echo ""

# Step 1: 시스템 업데이트
echo -e "${CYAN}📋 Step 1: 시스템 업데이트${NC}"
echo "─────────────────────────────────"
echo "시스템 패키지를 업데이트합니다..."
echo ""

sudo apt update
sudo apt upgrade -y

echo ""
echo -e "${GREEN}✅ 시스템 업데이트 완료${NC}"
echo ""

# Step 2: 필수 도구 설치
echo -e "${CYAN}📋 Step 2: 필수 도구 설치${NC}"
echo "─────────────────────────────────"
echo "build-essential, git, curl 등을 설치합니다..."
echo ""

sudo apt install -y \
    build-essential \
    wget \
    curl \
    git \
    unzip \
    software-properties-common

echo ""
echo -e "${GREEN}✅ 필수 도구 설치 완료${NC}"
echo ""

# Step 3: Python 3.10 설치
echo -e "${CYAN}📋 Step 3: Python 3.10 설치${NC}"
echo "─────────────────────────────────"

# Python 3.10 이미 설치되어 있는지 확인
if command -v python3.10 &> /dev/null; then
    PYTHON_VERSION=$(python3.10 --version)
    echo -e "${YELLOW}⚠️  Python 3.10이 이미 설치되어 있습니다${NC}"
    echo "   버전: $PYTHON_VERSION"
    echo ""
else
    echo "Python 3.10을 설치합니다..."
    echo ""

    # Python 3.10 저장소 추가
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update

    # Python 3.10 설치
    sudo apt install -y \
        python3.10 \
        python3.10-venv \
        python3.10-dev \
        python3-pip

    echo ""
    PYTHON_VERSION=$(python3.10 --version)
    echo -e "${GREEN}✅ Python 3.10 설치 완료: $PYTHON_VERSION${NC}"
    echo ""
fi

# Step 4: Tesseract OCR 설치
echo -e "${CYAN}📋 Step 4: Tesseract OCR 설치${NC}"
echo "─────────────────────────────────"

if command -v tesseract &> /dev/null; then
    TESSERACT_VERSION=$(tesseract --version 2>&1 | head -1)
    echo -e "${YELLOW}⚠️  Tesseract가 이미 설치되어 있습니다${NC}"
    echo "   버전: $TESSERACT_VERSION"
    echo ""
else
    echo "Tesseract OCR + 한글 언어팩을 설치합니다..."
    echo ""

    sudo apt install -y \
        tesseract-ocr \
        tesseract-ocr-kor \
        libtesseract-dev \
        poppler-utils

    echo ""
    TESSERACT_VERSION=$(tesseract --version 2>&1 | head -1)
    echo -e "${GREEN}✅ Tesseract 설치 완료: $TESSERACT_VERSION${NC}"
    echo ""
fi

# 한글 언어팩 확인
echo "설치된 언어팩 확인:"
tesseract --list-langs | grep kor && echo -e "${GREEN}✅ 한글 언어팩 설치됨${NC}" || echo -e "${RED}❌ 한글 언어팩 없음${NC}"
echo ""

# Step 5: 완료
echo -e "${CYAN}======================================${NC}"
echo -e "${GREEN}  ✅ 환경 설정 완료!${NC}"
echo -e "${CYAN}======================================${NC}"
echo ""
echo -e "${CYAN}🎯 다음 단계:${NC}"
echo ""
echo "  1. 프로젝트 복사:"
echo "     ${YELLOW}cp -r \"/mnt/c/Users/wnstn/OneDrive/Desktop/AI/AI-CHAT\" ~/AI-CHAT${NC}"
echo ""
echo "  2. 프로젝트 디렉토리로 이동:"
echo "     ${YELLOW}cd ~/AI-CHAT${NC}"
echo ""
echo "  3. 자동 설치 스크립트 실행:"
echo "     ${YELLOW}bash SETUP_NEW_PC.sh${NC}"
echo ""
echo -e "${CYAN}======================================${NC}"
echo ""

# 설치 정보 요약
echo -e "${CYAN}📊 설치된 패키지 정보:${NC}"
echo "─────────────────────────────────"
echo "Python: $(python3.10 --version 2>&1)"
echo "pip: $(pip3 --version 2>&1 | cut -d' ' -f1-2)"
echo "Tesseract: $(tesseract --version 2>&1 | head -1)"
echo "Git: $(git --version 2>&1)"
echo "─────────────────────────────────"
echo ""
