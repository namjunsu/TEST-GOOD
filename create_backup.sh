#\!/bin/bash
echo '🎯 AI-CHAT 백업 스크립트'
echo '========================'

# 백업 디렉토리 생성
BACKUP_DIR=~/ai-chat-backup-20250925
mkdir -p $BACKUP_DIR

echo '1. 소스코드 백업...'
tar -czf $BACKUP_DIR/source.tar.gz *.py *.md *.txt rag_system/ .streamlit/ --exclude='__pycache__'

echo '2. 설정 파일 백업...'
cp .env $BACKUP_DIR/ 2>/dev/null || echo '.env 파일 없음'
cp requirements_updated.txt $BACKUP_DIR/

echo '3. 대용량 파일 정보 저장...'
ls -la models/ > $BACKUP_DIR/models_list.txt
find docs -name '*.pdf' | wc -l > $BACKUP_DIR/pdf_count.txt

echo ''
echo '✅ 백업 완료: '$BACKUP_DIR
echo ''
echo '📦 대용량 파일 압축 (선택사항):'
echo '  tar -czf models.tar.gz models/  # 약 4GB, 10분 소요'
echo '  tar -czf docs.tar.gz docs/      # 약 200MB, 1분 소요'
echo ''
echo '💡 새 PC에서:'
echo '  1. Git clone 또는 source.tar.gz 압축 해제'
echo '  2. pip install -r requirements_updated.txt'
echo '  3. models/와 docs/ 폴더 복사'
echo '  4. streamlit run web_interface.py'

