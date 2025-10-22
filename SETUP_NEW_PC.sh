#!/bin/bash
# 신규 PC 자동 설치 스크립트
# 사용법: bash SETUP_NEW_PC.sh

set -e  # 오류 발생시 중단

echo "🚀 AI-CHAT 신규 PC 자동 설치 시작"
echo "=================================="
echo ""

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 0: OS 확인
echo "📋 Step 0: 시스템 정보 확인"
echo "─────────────────────────────────"
echo "OS: $(uname -s)"
echo "Architecture: $(uname -m)"
echo ""

# Step 1: Python 버전 확인
echo "📋 Step 1: Python 버전 확인"
echo "─────────────────────────────────"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3가 설치되어 있지 않습니다${NC}"
    echo ""
    echo "설치 방법:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    echo "  macOS: brew install python3"
    echo "  Windows: https://python.org 에서 다운로드"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python 버전: $PYTHON_VERSION"

# Python 3.8 이상인지 확인
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}❌ Python 3.8 이상이 필요합니다 (현재: $PYTHON_VERSION)${NC}"
    exit 1
fi

echo ""

# Step 2: 필수 시스템 패키지 확인
echo "📋 Step 2: 필수 시스템 패키지 확인"
echo "─────────────────────────────────"

# Tesseract OCR 확인
if ! command -v tesseract &> /dev/null; then
    echo -e "${YELLOW}⚠️  Tesseract OCR가 설치되어 있지 않습니다${NC}"
    echo ""
    echo "설치 방법:"
    echo "  Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-kor"
    echo "  macOS: brew install tesseract tesseract-lang"
    echo "  Windows: https://github.com/UB-Mannheim/tesseract/wiki"
    echo ""
    read -p "계속하시겠습니까? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ Tesseract OCR: $(tesseract --version | head -1)"
fi

echo ""

# Step 3: 가상환경 생성
echo "📋 Step 3: 가상환경 생성"
echo "─────────────────────────────────"

if [ -d ".venv" ]; then
    echo "⚠️  기존 .venv 폴더가 있습니다. 삭제하고 재생성합니다."
    rm -rf .venv
fi

python3 -m venv .venv
echo "✅ 가상환경 생성 완료"
echo ""

# Step 4: 가상환경 활성화 및 pip 업그레이드
echo "📋 Step 4: pip 업그레이드"
echo "─────────────────────────────────"

source .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate 2>/dev/null

pip install --upgrade pip setuptools wheel --quiet
echo "✅ pip 업그레이드 완료"
echo ""

# Step 5: 의존성 설치
echo "📋 Step 5: 패키지 설치 (5-10분 소요)"
echo "─────────────────────────────────"
echo "이 과정은 시간이 걸립니다. 기다려주세요..."
echo ""

# 개별 패키지 설치 (오류 발생시 어디서 멈췄는지 알 수 있음)
declare -a PACKAGES=(
    "streamlit==1.29.0"
    "python-dotenv==1.0.0"
    "pdfplumber==0.10.3"
    "pypdf==3.17.1"
    "pytesseract==0.3.10"
    "pdf2image==1.16.3"
    "faiss-cpu==1.7.4"
    "sentence-transformers==2.2.2"
    "chromadb==0.4.20"
    "rank-bm25==0.2.2"
    "scikit-learn==1.3.2"
    "llama-cpp-python==0.2.32"
    "numpy==1.24.3"
    "pandas==2.1.4"
    "tqdm==4.66.1"
    "Pillow==10.1.0"
    "loguru==0.7.2"
)

TOTAL=${#PACKAGES[@]}
CURRENT=0

for package in "${PACKAGES[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo -n "[$CURRENT/$TOTAL] 설치 중: $package ... "

    if pip install "$package" --quiet 2>/dev/null; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        echo ""
        echo -e "${RED}오류: $package 설치 실패${NC}"
        echo "수동으로 설치를 시도하세요:"
        echo "  pip install $package"
        exit 1
    fi
done

echo ""
echo "✅ 모든 패키지 설치 완료"
echo ""

# Step 6: 필수 파일 확인
echo "📋 Step 6: 필수 파일 확인"
echo "─────────────────────────────────"

REQUIRED_FILES=(
    "web_interface.py"
    "hybrid_chat_rag_v2.py"
    "quick_fix_rag.py"
    "config.py"
    ".env.production"
    "everything_index.db"
    "metadata.db"
)

ALL_FILES_OK=true

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo -e "${RED}❌ $file 없음${NC}"
        ALL_FILES_OK=false
    fi
done

if [ ! -d "docs" ]; then
    echo -e "${RED}❌ docs/ 폴더 없음${NC}"
    ALL_FILES_OK=false
else
    PDF_COUNT=$(find docs -name "*.pdf" 2>/dev/null | wc -l)
    echo "✅ docs/ 폴더 (PDF: ${PDF_COUNT}개)"
fi

if [ "$ALL_FILES_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  일부 파일이 없지만 계속 진행할 수 있습니다${NC}"
fi

echo ""

# Step 7: 시스템 테스트
echo "📋 Step 7: 시스템 테스트"
echo "─────────────────────────────────"

if [ -f "test_system.py" ]; then
    echo "테스트 실행 중..."
    echo ""

    if python3 test_system.py 2>&1 | grep -q "✅ 모든 테스트 통과"; then
        echo ""
        echo -e "${GREEN}✅ 시스템 테스트 통과!${NC}"
    else
        echo ""
        echo -e "${YELLOW}⚠️  일부 테스트 실패 (수동 확인 필요)${NC}"
    fi
else
    echo "⚠️  test_system.py 없음 (건너뜀)"
fi

echo ""

# Step 8: 완료
echo "=================================="
echo -e "${GREEN}✅ 설치 완료!${NC}"
echo "=================================="
echo ""
echo "🎯 다음 단계:"
echo ""
echo "1. 가상환경 활성화:"
echo "   source .venv/bin/activate"
echo ""
echo "2. 웹 인터페이스 시작:"
echo "   streamlit run web_interface.py --server.port 8501"
echo ""
echo "3. 브라우저에서 접속:"
echo "   http://localhost:8501"
echo ""
echo "=================================="
echo ""
echo "📖 문제 발생시:"
echo "   - TROUBLESHOOTING.md 참고"
echo "   - test_system.py 실행"
echo ""
