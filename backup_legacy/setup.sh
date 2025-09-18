#!/bin/bash

# AI-CHAT-V3 자동 설치 스크립트 (Linux/WSL2용)
# 사용법: bash setup.sh

set -e  # 오류 시 스크립트 중단

echo "🚀 AI-CHAT-V3 자동 설치를 시작합니다..."
echo "=================================="

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 1. 시스템 요구사항 확인
log_info "시스템 요구사항 확인 중..."

# Python 버전 확인
PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1-2)
REQUIRED_VERSION="3.9"

if [ -z "$PYTHON_VERSION" ]; then
    log_error "Python3가 설치되어 있지 않습니다."
    log_info "Python 3.9+ 설치 중..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv python3-dev
else
    log_success "Python $PYTHON_VERSION 확인됨"
fi

# 메모리 확인
MEMORY_GB=$(free -g | awk 'NR==2{print $2}')
if [ "$MEMORY_GB" -lt 8 ]; then
    log_warning "권장 메모리(8GB)보다 적습니다. 현재: ${MEMORY_GB}GB"
    log_info "스왑 파일 생성을 권장합니다."
else
    log_success "메모리 충족: ${MEMORY_GB}GB"
fi

# 디스크 공간 확인
DISK_GB=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$DISK_GB" -lt 10 ]; then
    log_error "디스크 공간 부족. 최소 10GB 필요, 현재: ${DISK_GB}GB"
    exit 1
else
    log_success "디스크 공간 충족: ${DISK_GB}GB"
fi

# 2. 필수 시스템 패키지 설치
log_info "필수 시스템 패키지 설치 중..."
sudo apt update
sudo apt install -y \
    build-essential \
    wget \
    curl \
    git \
    python3-dev \
    libffi-dev \
    libssl-dev \
    pkg-config

log_success "시스템 패키지 설치 완료"

# 3. 프로젝트 디렉토리 설정
PROJECT_DIR="$HOME/AI-CHAT-V3"
log_info "프로젝트 디렉토리 설정: $PROJECT_DIR"

if [ -d "$PROJECT_DIR" ]; then
    log_warning "기존 디렉토리가 있습니다. 백업 중..."
    mv "$PROJECT_DIR" "${PROJECT_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
log_success "프로젝트 디렉토리 생성 완료"

# 4. 마이그레이션 파일 복원
log_info "마이그레이션 파일 복원 중..."

# 현재 스크립트가 있는 디렉토리에서 파일 복사
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -d "$SCRIPT_DIR/core" ]; then
    cp "$SCRIPT_DIR"/core/* . 2>/dev/null || true
    cp -r "$SCRIPT_DIR/rag_system" . 2>/dev/null || true
    cp -r "$SCRIPT_DIR/docs" . 2>/dev/null || true
    cp "$SCRIPT_DIR"/config/* . 2>/dev/null || true
    log_success "마이그레이션 파일 복원 완료"
else
    log_error "마이그레이션 파일을 찾을 수 없습니다."
    log_info "setup.sh와 같은 디렉토리에 core/, rag_system/, docs/, config/ 폴더가 있는지 확인하세요."
    exit 1
fi

# 5. Python 가상환경 설정
log_info "Python 가상환경 생성 중..."
python3 -m venv ai-chat-env
source ai-chat-env/bin/activate
log_success "가상환경 생성 완료"

# 6. Python 패키지 설치
log_info "Python 패키지 설치 중... (시간이 걸릴 수 있습니다)"
pip install --upgrade pip setuptools wheel

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    log_success "패키지 설치 완료"
else
    log_error "requirements.txt 파일을 찾을 수 없습니다."
    exit 1
fi

# 7. 모델 디렉토리 생성
log_info "모델 디렉토리 생성 중..."
mkdir -p models
log_success "모델 디렉토리 생성 완료"

# 8. 모델 파일 다운로드 함수
download_model() {
    local filename="$1"
    local url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/$filename"
    local filepath="models/$filename"
    
    if [ -f "$filepath" ]; then
        log_warning "$filename 이미 존재합니다. 건너뛰기..."
        return 0
    fi
    
    log_info "$filename 다운로드 중... (약 2-4GB, 시간이 걸릴 수 있습니다)"
    
    # wget으로 다운로드 시도
    if command -v wget &> /dev/null; then
        wget --progress=bar:force:noscroll -O "$filepath" "$url"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "$filepath" "$url"
    else
        log_error "wget 또는 curl이 필요합니다."
        exit 1
    fi
    
    # 다운로드 검증
    if [ -f "$filepath" ] && [ -s "$filepath" ]; then
        log_success "$filename 다운로드 완료"
    else
        log_error "$filename 다운로드 실패"
        rm -f "$filepath"
        exit 1
    fi
}

# 9. 모델 파일 다운로드
log_info "Qwen2.5-7B 모델 다운로드 시작..."
download_model "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
download_model "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf"

# 10. 환경변수 파일 생성
log_info ".env 파일 생성 중..."
cat > .env << 'EOF'
MODEL_PATH=./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
DB_DIR=./rag_system/db
LOG_DIR=./rag_system/logs
API_KEY=broadcast-tech-rag-2025
STREAMLIT_SERVER_PORT=8501
EOF
log_success ".env 파일 생성 완료"

# 11. 로그 디렉토리 생성
log_info "로그 디렉토리 생성 중..."
mkdir -p rag_system/logs rag_system/db
log_success "로그 디렉토리 생성 완료"

# 12. 인덱스 구축
log_info "문서 인덱싱 시작... (시간이 걸릴 수 있습니다)"
if python3 build_index.py; then
    log_success "인덱싱 완료"
else
    log_error "인덱싱 실패"
    exit 1
fi

# 13. 시스템 테스트
log_info "시스템 테스트 중..."
if python3 -c "
import sys
sys.path.append('.')
try:
    from perfect_rag import PerfectRAG
    rag = PerfectRAG()
    print('시스템 테스트 성공')
except Exception as e:
    print(f'시스템 테스트 실패: {e}')
    sys.exit(1)
"; then
    log_success "시스템 테스트 통과"
else
    log_error "시스템 테스트 실패"
    exit 1
fi

# 14. 실행 스크립트 생성
log_info "실행 스크립트 생성 중..."
cat > run_ai_chat.sh << 'EOF'
#!/bin/bash
# AI-CHAT-V3 실행 스크립트

cd "$(dirname "$0")"
source ai-chat-env/bin/activate
echo "🚀 AI-CHAT-V3 웹 인터페이스를 시작합니다..."
echo "브라우저에서 http://localhost:8501 을 열어주세요"
streamlit run web_interface.py
EOF
chmod +x run_ai_chat.sh
log_success "실행 스크립트 생성 완료"

# 15. 설치 완료
echo ""
echo "🎉 AI-CHAT-V3 설치가 완료되었습니다!"
echo "=================================="
echo ""
echo "📁 설치 위치: $PROJECT_DIR"
echo "💾 디스크 사용량: $(du -sh "$PROJECT_DIR" | cut -f1)"
echo ""
echo "🚀 시스템 실행 방법:"
echo "1. 터미널에서 실행:"
echo "   cd $PROJECT_DIR"
echo "   source ai-chat-env/bin/activate"
echo "   streamlit run web_interface.py"
echo ""
echo "2. 간편 실행:"
echo "   cd $PROJECT_DIR && ./run_ai_chat.sh"
echo ""
echo "🌐 접속 주소: http://localhost:8501"
echo ""
echo "📚 도움말:"
echo "   - 마이그레이션 가이드: MIGRATION_GUIDE.md"
echo "   - 사용법: README.md"
echo "   - 개발 가이드: CLAUDE.md"
echo ""
echo "⚠️  주의사항:"
echo "   - 가상환경(ai-chat-env) 활성화 필요"
echo "   - 8501 포트가 사용 중이면 8502 포트 사용: --server.port 8502"
echo ""
log_success "설치 스크립트 실행 완료!"

# 자동 실행 여부 묻기
echo ""
read -p "지금 바로 웹 인터페이스를 실행하시겠습니까? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "웹 인터페이스 실행 중..."
    echo "브라우저에서 http://localhost:8501 을 열어주세요"
    echo "종료하려면 Ctrl+C를 누르세요"
    streamlit run web_interface.py
fi