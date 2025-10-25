#!/usr/bin/env bash
# ============================================================================
# AI-CHAT 시작 스크립트 (완전판)
# ============================================================================
# 기능:
# - 환경 검증 (Python, venv, 패키지)
# - DB 초기화 (WAL 설정)
# - 시스템 워밍업 (LLM, 인덱스)
# - Streamlit 웹 서버 시작
# ============================================================================

set -Eeuo pipefail

# 색상 정의
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# 경로 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 로그 함수
log_info() {
    echo -e "${GREEN}ℹ️  $*${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $*${NC}"
}

log_error() {
    echo -e "${RED}❌ $*${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $*${NC}"
}

# 에러 핸들러
error_handler() {
    log_error "스크립트 오류 발생 (라인 $1)"
    exit 1
}

trap 'error_handler $LINENO' ERR

# ============================================================================
# 1. 환경 검증
# ============================================================================

log_info "AI-CHAT 시스템 시작 중..."
echo ""

# Python 버전 확인
log_info "Python 버전 확인..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11.0"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    log_error "Python 3.11 이상이 필요합니다. (현재: $python_version)"
    exit 1
fi
log_success "Python $python_version"

# 가상환경 확인
log_info "가상환경 확인..."
if [ ! -d .venv ]; then
    log_error "가상환경이 없습니다."
    log_info "다음 명령으로 생성하세요: python3 -m venv .venv"
    exit 1
fi
log_success "가상환경 발견: .venv"

# 가상환경 활성화
log_info "가상환경 활성화..."
source .venv/bin/activate
log_success "가상환경 활성화됨"

# 필수 패키지 확인
log_info "필수 패키지 확인..."
if ! python3 -c "import streamlit, pydantic" 2>/dev/null; then
    log_warn "필수 패키지가 설치되지 않았습니다."
    log_info "설치 중... (pip install -r requirements.txt)"
    pip install -q -r requirements.txt
fi
log_success "패키지 설치 확인 완료"

# ============================================================================
# 2. 디렉터리 생성
# ============================================================================

log_info "필수 디렉터리 생성..."
mkdir -p var/log
mkdir -p var/db
mkdir -p models
mkdir -p docs
log_success "디렉터리 준비 완료"

# ============================================================================
# 3. 시스템 점검 (옵션)
# ============================================================================

if [ -f "app/ops/system_check.py" ]; then
    log_info "시스템 점검 실행..."
    if python3 -m app.ops.system_check 2>&1 | tee -a var/log/system_check.log; then
        log_success "시스템 점검 통과"
    else
        log_warn "시스템 점검에서 경고 발견"
        read -p "계속 진행하시겠습니까? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "사용자 취소"
            exit 0
        fi
    fi
else
    log_warn "system_check.py 없음 (건너뜀)"
fi

# ============================================================================
# 4. 데이터베이스 초기화
# ============================================================================

log_info "데이터베이스 설정 중..."

# Python으로 DB 초기화
python3 << 'PYTHON_EOF'
import sys
import sqlite3
from pathlib import Path

# DB 경로
db_path = Path("var/db/metadata.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

# WAL 모드 설정
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA busy_timeout=5000;")

# 기본 테이블 생성 (필요시)
conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id TEXT UNIQUE NOT NULL,
        title TEXT,
        category TEXT,
        year INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()
conn.close()

print("✅ WAL 모드 설정 완료")
PYTHON_EOF

log_success "데이터베이스 준비 완료"

# ============================================================================
# 5. 워밍업 (옵션)
# ============================================================================

if [ "${SKIP_WARMUP:-0}" = "0" ]; then
    log_info "시스템 워밍업 중... (첫 응답 지연 제거)"

    # Python으로 워밍업
    python3 << 'PYTHON_EOF' 2>&1 | tee -a var/log/warmup.log || true
import sys
sys.path.insert(0, ".")

try:
    # Config 로드
    from config import Config
    cfg = Config.get_instance()
    print("✅ Config 로드 완료")

    # RAG 파이프라인 로드 (있으면)
    try:
        from app.rag.pipeline import RagPipeline
        pipeline = RagPipeline(cfg)
        pipeline.warmup()
        print("✅ RAG 워밍업 완료")
    except ImportError:
        print("⚠️  app.rag.pipeline 없음 (구조 전환 전)")

except Exception as e:
    print(f"⚠️  워밍업 실패 (무시): {e}")
PYTHON_EOF

    log_success "워밍업 완료 (또는 건너뜀)"
else
    log_warn "워밍업 건너뜀 (SKIP_WARMUP=1)"
fi

# ============================================================================
# 6. Streamlit 실행
# ============================================================================

echo ""
log_info "Streamlit 웹 서버 시작 중..."
echo ""
echo "========================================="
echo "📌 접속 주소:"
echo "   로컬: http://localhost:8501"
echo "   네트워크: http://$(hostname -I | awk '{print $1}'):8501"
echo "========================================="
echo ""
echo "종료하려면: Ctrl + C"
echo ""

# 메인 웹 인터페이스 찾기
WEB_INTERFACE=""
if [ -f "app/ui/web_app.py" ]; then
    WEB_INTERFACE="app/ui/web_app.py"
elif [ -f "web_interface.py" ]; then
    WEB_INTERFACE="web_interface.py"
else
    log_error "웹 인터페이스 파일을 찾을 수 없습니다."
    exit 1
fi

log_info "실행: streamlit run $WEB_INTERFACE"

# Streamlit 실행
exec streamlit run "$WEB_INTERFACE" \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    2>&1 | tee -a var/log/streamlit.log
