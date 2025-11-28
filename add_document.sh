#!/usr/bin/env bash
# 신규 문서 추가 스크립트
# 사용법: ./add_document.sh <PDF파일경로>

set -e

if [ $# -eq 0 ]; then
    echo "사용법: ./add_document.sh <PDF파일경로>"
    echo "예시: ./add_document.sh docs/year_2025/2025-08-13_TVLogic_모니터_구매_검토서.pdf"
    exit 1
fi

PDF_PATH="$1"
FILENAME=$(basename "$PDF_PATH")

if [ ! -f "$PDF_PATH" ]; then
    echo "❌ 파일이 없습니다: $PDF_PATH"
    exit 1
fi

echo "=== 신규 문서 추가: $FILENAME ==="

# 1. DB에서 기존 레코드 삭제 (있으면)
echo "1. DB에서 기존 레코드 삭제 중..."
sqlite3 metadata.db "DELETE FROM documents WHERE filename = '$FILENAME';" || true
sqlite3 metadata.db "DELETE FROM documents WHERE normalized_filename = '$FILENAME';" || true
sqlite3 metadata.db "DELETE FROM documents_fts WHERE path LIKE '%$FILENAME%';" || true

# 2. incoming 폴더에 복사
echo "2. incoming 폴더에 복사 중..."
mkdir -p docs/incoming
cp "$PDF_PATH" docs/incoming/

# 3. ingest 실행
echo "3. ingest 실행 중..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$SCRIPT_DIR" "$SCRIPT_DIR/.venv/bin/python" scripts/core/ingest_from_docs.py

# 4. 확인
echo "4. DB 확인 중..."
COUNT=$(sqlite3 metadata.db "SELECT COUNT(*) FROM documents WHERE filename LIKE '%${FILENAME}%';")

if [ "$COUNT" -gt 0 ]; then
    echo "✅ 성공! $FILENAME이 DB에 추가되었습니다 (${COUNT}개)"
    sqlite3 metadata.db "SELECT id, filename, year, category FROM documents WHERE filename LIKE '%${FILENAME}%';"
else
    echo "❌ 실패! $FILENAME이 DB에 추가되지 않았습니다"
    exit 1
fi

echo ""
echo "📋 다음 단계:"
echo "   1. 웹 브라우저에서 http://localhost:8501 접속"
echo "   2. Ctrl+Shift+R (강제 새로고침)"
echo "   3. 사이드바에서 문서 확인"
