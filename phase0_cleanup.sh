#!/bin/bash
# Phase 0: 프로젝트 대청소
echo "🧹 Phase 0: 프로젝트 대청소 시작"
echo "================================="

# 백업 디렉토리 생성
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# 1. archive 폴더 전체 백업 후 삭제
if [ -d "archive" ]; then
    echo "📦 archive 폴더 백업 후 삭제..."
    mv archive $BACKUP_DIR/
fi

# 2. 테스트 파일들 백업 후 삭제
echo "🧪 테스트 파일 정리..."
find . -name "*test*.py" -type f -exec mv {} $BACKUP_DIR/ \; 2>/dev/null

# 3. 기타 불필요한 파일들 삭제
echo "🗑️ 불필요한 파일 삭제..."
rm -f cleanup_analysis.py
rm -f cleanup_plan.json
rm -f organize_project.py
rm -f deep_clean.py
rm -f complete_cleanup.py

# 4. __pycache__ 삭제
echo "🧹 캐시 정리..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# 5. 빈 디렉토리 삭제
find . -type d -empty -delete 2>/dev/null

echo "✅ 정리 완료!"
echo ""
echo "📊 결과:"
echo "- Python 파일: $(find . -name '*.py' -type f | grep -v __pycache__ | wc -l)개"
echo "- 백업 위치: $BACKUP_DIR"