#!/bin/bash
# H100 워크스테이션 복원 스크립트
# 사용법: ./scripts/ops/migrate_restore.sh [백업_디렉토리] [프로젝트_디렉토리]

set -e

BACKUP_DIR="${1:-/tmp/ai-chat-backup}"
PROJECT_DIR="${2:-/home/$USER/AI-CHAT}"

echo "=========================================="
echo "AI-CHAT 데이터 복원 시작"
echo "=========================================="
echo "백업 위치: $BACKUP_DIR"
echo "프로젝트: $PROJECT_DIR"
echo ""

# 체크섬 검증
echo "[0/5] 체크섬 검증..."
cd "$BACKUP_DIR"
if [ -f "checksums.md5" ]; then
    if md5sum -c checksums.md5; then
        echo "  - 체크섬 검증 통과"
    else
        echo "  - 체크섬 불일치! 백업 파일 손상 가능"
        exit 1
    fi
else
    echo "  - 체크섬 파일 없음 (스킵)"
fi
echo ""

# 프로젝트 디렉토리 생성
mkdir -p "$PROJECT_DIR/data"

# 1. 메타데이터 DB 복원
echo "[1/5] 메타데이터 DB 복원..."
cp "$BACKUP_DIR/metadata.db" "$PROJECT_DIR/"
echo "  - metadata.db 복원 완료"

# 2. 추출 텍스트 복원
echo "[2/5] 추출 텍스트 복원..."
tar -xzf "$BACKUP_DIR/extracted.tar.gz" -C "$PROJECT_DIR/data/"
echo "  - data/extracted/ 복원 완료"

# 3. PDF 문서 복원
echo "[3/5] PDF 문서 복원..."
tar -xzf "$BACKUP_DIR/docs.tar.gz" -C "$PROJECT_DIR/"
echo "  - docs/ 복원 완료"

# 4. 인덱스 복원
echo "[4/5] 인덱스 복원..."
tar -xzf "$BACKUP_DIR/var.tar.gz" -C "$PROJECT_DIR/"
echo "  - var/ 복원 완료"

# 5. 설정 파일 복원
echo "[5/5] 설정 파일 복원..."
if [ -d "$BACKUP_DIR/config" ]; then
    cp "$BACKUP_DIR/config/.env" "$PROJECT_DIR/" 2>/dev/null || true
    echo "  - .env 복원 완료"
fi

# config yaml 파일 복원
if [ -f "$BACKUP_DIR/config_yaml.tar.gz" ]; then
    tar -xzf "$BACKUP_DIR/config_yaml.tar.gz" -C "$PROJECT_DIR/"
    echo "  - config/*.yaml 복원 완료"
fi

echo ""
echo "=========================================="
echo "복원 완료! 검증 중..."
echo "=========================================="

# 검증
echo "문서 수: $(sqlite3 "$PROJECT_DIR/metadata.db" 'SELECT COUNT(*) FROM documents')"
echo "텍스트 파일: $(ls "$PROJECT_DIR/data/extracted/"*.txt 2>/dev/null | wc -l)개"
echo "PDF 파일: $(find "$PROJECT_DIR/docs" -name "*.pdf" | wc -l)개"

echo ""
echo "=========================================="
echo "다음 단계"
echo "=========================================="
echo "1. Python 환경 설정:"
echo "   cd $PROJECT_DIR"
echo "   python -m venv .venv"
echo "   source .venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "2. vLLM 설치 (H100용):"
echo "   pip install vllm"
echo ""
echo "3. 모델 다운로드:"
echo "   # RAG용"
echo "   vllm serve Qwen/Qwen2.5-32B-Instruct --port 8000"
echo "   # OCR용 (선택)"
echo "   vllm serve Qwen/Qwen2-VL-7B-Instruct --port 8001"
echo ""
echo "4. 앱 실행:"
echo "   streamlit run app_main.py"
