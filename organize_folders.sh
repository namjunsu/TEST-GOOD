#!/bin/bash

# 1. 백업 폴더 생성
mkdir -p backup/old_files

# 2. 사용하지 않는 파일들 백업
echo "🗂️ 사용하지 않는 파일 백업 중..."

# 레거시 파일들
mv asset_cache.py backup/old_files/ 2>/dev/null
mv query_logger.py backup/old_files/ 2>/dev/null
mv improve_answer_quality.py backup/old_files/ 2>/dev/null
mv download_models.py backup/old_files/ 2>/dev/null
mv validate_migration.py backup/old_files/ 2>/dev/null
mv setup.bat backup/old_files/ 2>/dev/null
mv setup.sh backup/old_files/ 2>/dev/null
mv setup_wsl2_network.bat backup/old_files/ 2>/dev/null

# 3. 자산 데이터 정리
echo "📊 자산 데이터 정리 중..."
mkdir -p docs/assets
find docs -name "*자산*.txt" -exec mv {} docs/assets/ \; 2>/dev/null
find docs -name "*7904*.txt" -exec mv {} docs/assets/ \; 2>/dev/null

# 4. 로그 파일 정리
echo "📝 로그 파일 정리 중..."
find . -name "*.log" -exec mv {} logs/ \; 2>/dev/null

echo "✅ 폴더 정리 완료!"
