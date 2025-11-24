#!/bin/bash
# 새 문서 추가 헬퍼 스크립트
# 사용법: bash scripts/add_new_document.sh /path/to/문서.pdf

set -e  # 에러 시 중단

if [ $# -eq 0 ]; then
    echo "❌ 사용법: bash scripts/add_new_document.sh <PDF파일경로>"
    echo "예시: bash scripts/add_new_document.sh ~/Downloads/2025-01-01_새문서.pdf"
    exit 1
fi

PDF_FILE="$1"

if [ ! -f "$PDF_FILE" ]; then
    echo "❌ 파일이 존재하지 않습니다: $PDF_FILE"
    exit 1
fi

echo "============================================"
echo "📄 새 문서 추가 프로세스 시작"
echo "============================================"
echo ""

# 1단계: incoming 폴더로 복사
echo "1️⃣ 파일을 docs/incoming/으로 복사 중..."
cp "$PDF_FILE" docs/incoming/
FILENAME=$(basename "$PDF_FILE")
echo "✅ 복사 완료: $FILENAME"
echo ""

# 2단계: 문서 인제스트
echo "2️⃣ 문서 메타데이터 추출 및 DB 등록 중..."
python3 scripts/ingest_from_docs.py
echo ""

# 3단계: DB 확인
echo "3️⃣ DB 상태 확인..."
DOC_COUNT=$(sqlite3 metadata.db "SELECT COUNT(*) FROM documents;")
echo "   현재 DB 문서 수: ${DOC_COUNT}개"
echo ""

# 4단계: year 컬럼 업데이트 (date에서 추출)
echo "4️⃣ year 컬럼 업데이트 중..."
sqlite3 metadata.db "UPDATE documents SET year = CASE WHEN date LIKE '____-__-__' THEN substr(date, 1, 4) ELSE year END WHERE year = '정보 없' OR year IS NULL OR year = '';"
echo "✅ year 컬럼 업데이트 완료"
echo ""

# 5단계: BM25 인덱스 재빌드
echo "5️⃣ BM25 검색 인덱스 재빌드 중..."
python3 scripts/reindex_atomic.py 2>&1 | grep -E "(대상|완료|BM25)" | tail -5
echo "✅ 인덱스 재빌드 완료"
echo ""

# 6단계: 최종 확인
echo "============================================"
echo "✅ 문서 추가 완료!"
echo "============================================"
echo ""
echo "📊 최종 상태:"
echo "   - DB 문서 수: ${DOC_COUNT}개"
echo "   - 추가된 파일: $FILENAME"
echo ""
echo "💡 웹 인터페이스를 새로고침하면 새 문서를 볼 수 있습니다."
echo "   URL: http://localhost:8501"
echo ""
