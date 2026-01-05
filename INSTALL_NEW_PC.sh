#!/bin/bash
# ==========================================
# AI-CHAT 새 PC 자동 설치 스크립트
# ==========================================
# 사용법: ./INSTALL_NEW_PC.sh
# 요구사항: Ubuntu 20.04+ (sudo 권한 필요)
# ==========================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo -e "${BLUE}AI-CHAT 자동 설치 프로그램${NC}"
echo "=========================================="
echo ""

# 현재 디렉토리 확인
INSTALL_DIR=$(pwd)
echo -e "${YELLOW}설치 경로:${NC} $INSTALL_DIR"
echo ""

# ==========================================
# 1단계: 시스템 패키지 설치
# ==========================================
echo -e "${YELLOW}[1/6] 시스템 패키지 설치 중...${NC}"
echo "관리자 권한이 필요합니다."

# 이미 설치된 패키지는 건너뜀
if ! command -v python3.10 &> /dev/null; then
    echo "Python 3.10 설치 중..."
    sudo apt update
    sudo apt install -y python3.10 python3.10-venv python3-pip
else
    echo -e "${GREEN}✓ Python 3.10 이미 설치됨${NC}"
fi

# Tesseract OCR (한글 지원)
if ! command -v tesseract &> /dev/null; then
    echo "Tesseract OCR 설치 중..."
    sudo apt install -y tesseract-ocr tesseract-ocr-kor
else
    echo -e "${GREEN}✓ Tesseract OCR 이미 설치됨${NC}"
fi

# Poppler (PDF 처리)
if ! command -v pdftotext &> /dev/null; then
    echo "Poppler 설치 중..."
    sudo apt install -y poppler-utils
else
    echo -e "${GREEN}✓ Poppler 이미 설치됨${NC}"
fi

# NTFS 지원 (외장하드용)
if ! dpkg -l | grep -q ntfs-3g; then
    echo "NTFS 드라이버 설치 중..."
    sudo apt install -y ntfs-3g
else
    echo -e "${GREEN}✓ NTFS 드라이버 이미 설치됨${NC}"
fi

echo -e "${GREEN}✓ 시스템 패키지 설치 완료${NC}"
echo ""

# ==========================================
# 2단계: Python 가상환경 생성
# ==========================================
echo -e "${YELLOW}[2/6] Python 가상환경 생성 중...${NC}"

if [ -d ".venv" ]; then
    echo -e "${YELLOW}⚠ 기존 .venv 발견. 삭제 후 재생성합니다.${NC}"
    rm -rf .venv
fi

python3 -m venv .venv
source .venv/bin/activate

echo -e "${GREEN}✓ 가상환경 생성 완료${NC}"
echo ""

# ==========================================
# 3단계: Python 패키지 설치
# ==========================================
echo -e "${YELLOW}[3/6] Python 패키지 설치 중...${NC}"
echo "이 단계는 5~10분 소요될 수 있습니다."
echo ""

# pip 업그레이드
pip install --upgrade pip setuptools wheel

# requirements.txt 설치
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Python 패키지 설치 완료${NC}"
else
    echo -e "${RED}✗ requirements.txt 파일을 찾을 수 없습니다!${NC}"
    exit 1
fi
echo ""

# ==========================================
# 4단계: .env 파일 자동 설정
# ==========================================
echo -e "${YELLOW}[4/6] 환경 설정 파일(.env) 수정 중...${NC}"

if [ -f ".env" ]; then
    # 백업 생성
    cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

    # 경로 자동 수정 (현재 디렉토리 기준)
    sed -i "s|MODEL_PATH=.*|MODEL_PATH=$INSTALL_DIR/models|g" .env
    sed -i "s|LLM_MODEL_PATH=.*|LLM_MODEL_PATH=$INSTALL_DIR/models|g" .env
    sed -i "s|VLLM_MODEL_PATH=.*|VLLM_MODEL_PATH=$INSTALL_DIR/models|g" .env

    echo -e "${GREEN}✓ .env 파일 경로 자동 수정 완료${NC}"
    echo "  MODEL_PATH=$INSTALL_DIR/models"
else
    echo -e "${RED}✗ .env 파일을 찾을 수 없습니다!${NC}"
    echo "  .env.example 파일이 있다면 복사하여 사용하세요:"
    echo "  cp .env.example .env"
    exit 1
fi
echo ""

# ==========================================
# 5단계: GPU 확인 (선택적)
# ==========================================
echo -e "${YELLOW}[5/6] GPU 확인 중...${NC}"

if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU 감지됨${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    echo ""
    echo "GPU 메모리에 맞게 .env 파일을 수정할 수 있습니다:"
    echo "  VLLM_GPU_MEMORY_UTILIZATION=0.90  # GPU 메모리 활용률 (0.7~0.95)"
else
    echo -e "${YELLOW}⚠ GPU를 찾을 수 없습니다. CPU 모드로 실행됩니다.${NC}"
    echo "GPU 사용을 원하시면 NVIDIA 드라이버를 설치하세요."
fi
echo ""

# ==========================================
# 6단계: 권한 설정
# ==========================================
echo -e "${YELLOW}[6/6] 실행 권한 설정 중...${NC}"

chmod +x start_ai_chat.sh
if [ -f "backup_to_external.sh" ]; then
    chmod +x backup_to_external.sh
fi

echo -e "${GREEN}✓ 권한 설정 완료${NC}"
echo ""

# ==========================================
# 설치 완료
# ==========================================
echo "=========================================="
echo -e "${GREEN}✅ AI-CHAT 설치 완료!${NC}"
echo "=========================================="
echo ""
echo -e "${BLUE}📌 실행 방법:${NC}"
echo ""
echo "1. 가상환경 활성화 (매번 필요):"
echo "   source .venv/bin/activate"
echo ""
echo "2. AI-CHAT 시작:"
echo "   ./start_ai_chat.sh"
echo ""
echo -e "${BLUE}📌 주요 파일 위치:${NC}"
echo "  모델: $INSTALL_DIR/models/"
echo "  문서: $INSTALL_DIR/docs/"
echo "  설정: $INSTALL_DIR/.env"
echo ""
echo -e "${BLUE}📌 문제 해결:${NC}"
echo "  - 모델 파일 확인: ls -lh $INSTALL_DIR/models/"
echo "  - 로그 확인: tail -f logs/app.log"
echo "  - 설정 수정: nano .env"
echo ""
echo -e "${YELLOW}⚠ 참고사항:${NC}"
echo "  - 처음 실행 시 모델 로딩에 1~2분 소요될 수 있습니다."
echo "  - 웹 인터페이스: http://localhost:8501"
echo "  - API 엔드포인트: http://localhost:7860"
echo ""
echo "설치가 완료되었습니다. 즐거운 AI 대화 되세요! 🚀"
echo "=========================================="
