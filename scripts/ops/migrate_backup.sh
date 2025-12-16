#!/bin/bash
# H100 워크스테이션 이전용 백업 스크립트
# 사용법: ./scripts/ops/migrate_backup.sh [백업_디렉토리]

set -e

BACKUP_DIR="${1:-/tmp/ai-chat-backup-$(date +%Y%m%d_%H%M%S)}"
PROJECT_DIR="/home/wnstn4647/AI-CHAT"

echo "=========================================="
echo "AI-CHAT 이전용 백업 시작"
echo "=========================================="
echo "백업 위치: $BACKUP_DIR"
echo ""

mkdir -p "$BACKUP_DIR"

# 1. 필수 데이터 백업
echo "[1/5] 필수 데이터 백업..."
cp "$PROJECT_DIR/metadata.db" "$BACKUP_DIR/"
echo "  - metadata.db ($(du -h "$BACKUP_DIR/metadata.db" | cut -f1))"

# 2. 추출된 텍스트 백업
echo "[2/5] 추출 텍스트 백업..."
tar -czf "$BACKUP_DIR/extracted.tar.gz" -C "$PROJECT_DIR/data" extracted/
echo "  - extracted.tar.gz ($(du -h "$BACKUP_DIR/extracted.tar.gz" | cut -f1))"

# 3. PDF 문서 백업
echo "[3/5] PDF 문서 백업..."
tar -czf "$BACKUP_DIR/docs.tar.gz" -C "$PROJECT_DIR" docs/
echo "  - docs.tar.gz ($(du -h "$BACKUP_DIR/docs.tar.gz" | cut -f1))"

# 4. 인덱스 백업
echo "[4/5] 인덱스 백업..."
tar -czf "$BACKUP_DIR/var.tar.gz" -C "$PROJECT_DIR" var/
echo "  - var.tar.gz ($(du -h "$BACKUP_DIR/var.tar.gz" | cut -f1))"

# 5. 설정 파일 백업
echo "[5/5] 설정 파일 백업..."
mkdir -p "$BACKUP_DIR/config"
cp "$PROJECT_DIR/.env" "$BACKUP_DIR/config/" 2>/dev/null || echo "  - .env 없음 (스킵)"
cp "$PROJECT_DIR/requirements.txt" "$BACKUP_DIR/config/"

# config 폴더의 yaml 파일들 백업 (도메인 설정 등)
if [ -d "$PROJECT_DIR/config" ]; then
    tar -czf "$BACKUP_DIR/config_yaml.tar.gz" -C "$PROJECT_DIR" config/*.yaml config/*.py 2>/dev/null
    echo "  - config_yaml.tar.gz ($(du -h "$BACKUP_DIR/config_yaml.tar.gz" | cut -f1))"
fi

# 6. 검증
echo ""
echo "=========================================="
echo "백업 검증"
echo "=========================================="
echo "백업 파일 목록:"
ls -lh "$BACKUP_DIR"
echo ""
echo "총 백업 크기: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""

# 7. 체크섬 생성
echo "체크섬 생성 중..."
cd "$BACKUP_DIR"
md5sum metadata.db *.tar.gz > checksums.md5
echo "  - checksums.md5 생성 완료"

echo ""
echo "=========================================="
echo "백업 완료!"
echo "=========================================="
echo ""
echo "새 서버에서 복원 명령어:"
echo "  scp -r $BACKUP_DIR user@new-server:/path/to/backup"
echo ""
echo "또는 USB로 복사:"
echo "  cp -r $BACKUP_DIR /media/usb/"
