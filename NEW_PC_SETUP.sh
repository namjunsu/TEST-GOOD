#!/bin/bash
# ================================================
# AI-CHAT 새 PC WSL 환경 완전 설정 스크립트
# ================================================

echo "🚀 AI-CHAT 새 PC 설정 시작..."
echo "================================="

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 시스템 업데이트
echo -e "${YELLOW}[1/8] 시스템 업데이트...${NC}"
sudo apt-get update

# 2. Python 3.10 설치 (WSL 기본은 보통 3.8)
echo -e "${YELLOW}[2/8] Python 3.10 설치...${NC}"
sudo apt-get install -y python3.10 python3.10-venv python3-pip

# 3. 필수 시스템 패키지 설치
echo -e "${YELLOW}[3/8] 필수 시스템 패키지 설치...${NC}"
sudo apt-get install -y \
    build-essential \
    gcc \
    g++ \
    cmake \
    git \
    curl \
    wget \
    tesseract-ocr \
    tesseract-ocr-kor \
    poppler-utils \
    libgomp1 \
    libpoppler-cpp-dev

# 4. CUDA 설치 (선택사항 - GPU 있는 경우만)
echo -e "${YELLOW}[4/8] GPU 확인...${NC}"
if nvidia-smi &>/dev/null; then
    echo -e "${GREEN}✓ GPU 감지됨. CUDA 이미 설치됨.${NC}"
else
    echo -e "${YELLOW}GPU가 없거나 드라이버가 설치되지 않았습니다.${NC}"
    echo "GPU 사용하려면 나중에 수동으로 설치하세요:"
    echo "  1. Windows에서 NVIDIA 드라이버 설치"
    echo "  2. WSL에서 CUDA Toolkit 설치"
fi

# 5. 프로젝트 압축 해제
echo -e "${YELLOW}[5/8] 프로젝트 압축 해제...${NC}"
if [ -f "ai-chat-complete.tar.gz" ]; then
    tar -xzf ai-chat-complete.tar.gz
    echo -e "${GREEN}✓ 압축 해제 완료${NC}"
else
    echo -e "${RED}⚠ ai-chat-complete.tar.gz 파일을 먼저 복사하세요!${NC}"
    exit 1
fi

# 6. Python 가상환경 생성 및 활성화
echo -e "${YELLOW}[6/8] Python 가상환경 설정...${NC}"
cd AI-CHAT || exit
python3.10 -m venv venv
source venv/bin/activate

# 7. Python 패키지 설치
echo -e "${YELLOW}[7/8] Python 패키지 설치 (5-10분 소요)...${NC}"
pip install --upgrade pip
pip install -r requirements_updated.txt

# GPU 있으면 CUDA 버전 llama-cpp 재설치
if nvidia-smi &>/dev/null; then
    echo -e "${YELLOW}GPU용 llama-cpp-python 재설치...${NC}"
    pip uninstall -y llama-cpp-python
    CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python==0.2.28
fi

# 8. 디렉토리 권한 설정
echo -e "${YELLOW}[8/8] 디렉토리 생성 및 권한 설정...${NC}"
mkdir -p cache indexes logs rag_system/db
chmod -R 755 .

# 완료!
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}✅ 설정 완료!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "실행 방법:"
echo "  cd AI-CHAT"
echo "  source venv/bin/activate"
echo "  streamlit run web_interface.py"
echo ""
echo "브라우저에서 http://localhost:8501 접속"
echo ""

# 파일 체크
echo "파일 확인:"
echo "  모델: $(du -sh models/ 2>/dev/null || echo '❌ models 폴더 없음')"
echo "  문서: $(find docs -name '*.pdf' 2>/dev/null | wc -l)개 PDF"
echo ""