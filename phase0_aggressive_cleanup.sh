#!/bin/bash
# Phase 0: Aggressive Cleanup - 진짜 필수 파일만 남기기
echo "🧹 Phase 0: Aggressive Cleanup 시작"
echo "================================="
echo "⚠️  WARNING: 12개 필수 파일 제외하고 모두 삭제됩니다!"
echo ""

# 백업 디렉토리 생성
BACKUP_DIR="backup_final_$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# 필수 파일 목록
ESSENTIAL_FILES=(
    "web_interface.py"
    "config.py"
    "requirements_updated.txt"
    "rag_core.py"
    "document_processor.py"
    "vector_store.py"
    "search_engine.py"
    "llm_handler.py"
    "log_system.py"
    "Dockerfile"
)

# 필수 디렉토리
ESSENTIAL_DIRS=(
    ".streamlit"
    "docs"
    "models"
    "indexes"
    "logs"
)

echo "📦 Python 파일 백업 중..."
# 모든 Python 파일 백업
find . -maxdepth 1 -name "*.py" -type f | while read file; do
    filename=$(basename "$file")
    # 필수 파일이 아니면 백업
    if [[ ! " ${ESSENTIAL_FILES[@]} " =~ " ${filename} " ]]; then
        echo "  백업: $filename"
        mv "$file" "$BACKUP_DIR/"
    fi
done

echo ""
echo "📦 불필요한 파일 정리..."
# 모든 perfect_rag.py 백업 (새 시스템과 충돌 방지)
if [ -f "perfect_rag.py" ]; then
    echo "  이전 RAG 시스템 백업: perfect_rag.py"
    mv perfect_rag.py "$BACKUP_DIR/"
fi

# rag_system 폴더 백업
if [ -d "rag_system" ]; then
    echo "  이전 rag_system 폴더 백업"
    mv rag_system "$BACKUP_DIR/"
fi

# archive 폴더 백업
if [ -d "archive" ]; then
    echo "  archive 폴더 백업"
    mv archive "$BACKUP_DIR/"
fi

# 테스트 파일들 정리
find . -name "*test*.py" -type f -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null
find . -name "*Test*.py" -type f -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null

# 기타 불필요한 파일들
rm -f *.log 2>/dev/null
rm -f *.bak 2>/dev/null
rm -f *.tmp 2>/dev/null
rm -f *.swp 2>/dev/null
rm -f .DS_Store 2>/dev/null

# __pycache__ 삭제
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# 빈 디렉토리 삭제 (필수 디렉토리 제외)
find . -type d -empty ! -path "./docs*" ! -path "./models*" ! -path "./indexes*" ! -path "./logs*" ! -path "./.streamlit*" -delete 2>/dev/null

echo ""
echo "📂 필수 디렉토리 확인..."
for dir in "${ESSENTIAL_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "  생성: $dir"
        mkdir -p "$dir"
    else
        echo "  ✓ $dir"
    fi
done

# indexes 디렉토리 초기화
mkdir -p indexes

echo ""
echo "✅ 정리 완료!"
echo ""
echo "📊 최종 결과:"
echo "- Python 파일: $(find . -maxdepth 1 -name '*.py' -type f | wc -l)개"
echo "- 백업 위치: $BACKUP_DIR"
echo "- 백업된 파일: $(ls $BACKUP_DIR 2>/dev/null | wc -l)개"
echo ""
echo "📝 필수 파일 목록:"
for file in "${ESSENTIAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (없음)"
    fi
done