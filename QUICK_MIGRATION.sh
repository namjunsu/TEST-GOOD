#!/bin/bash
# AI-CHAT 프로젝트 빠른 이전 스크립트

echo "🚀 AI-CHAT 프로젝트 이전 준비"
echo "="
echo ""

# Step 1: 백그라운드 프로세스 종료
echo "1️⃣ 실행 중인 프로세스 종료..."
pkill -f streamlit 2>/dev/null
pkill -f build_cache 2>/dev/null
pkill -f "everything_like_search" 2>/dev/null
sleep 2
echo "✅ 완료"
echo ""

# Step 2: 백업 파일명 생성
BACKUP_NAME="AI-CHAT_backup_$(date +%Y%m%d_%H%M).tar.gz"
echo "2️⃣ 프로젝트 압축 중..."
echo "   파일명: $BACKUP_NAME"
echo "   크기: 16GB (5-10분 소요)"
echo ""

cd /home/wnstn4647

# Step 3: 압축
tar -czf "$BACKUP_NAME" \
  --exclude='AI-CHAT/.venv' \
  --exclude='AI-CHAT/__pycache__' \
  --exclude='AI-CHAT/*/__pycache__' \
  --exclude='AI-CHAT/.git' \
  --exclude='AI-CHAT/unused_files' \
  AI-CHAT/

if [ $? -eq 0 ]; then
    echo "✅ 압축 완료"
    echo ""

    # Step 4: 결과 표시
    echo "3️⃣ 백업 파일 정보:"
    ls -lh "$BACKUP_NAME"
    echo ""

    echo "📋 다음 단계:"
    echo "─────────────────────────────────────────"
    echo "1. USB/외장하드를 연결하세요"
    echo "2. 백업 파일을 복사하세요:"
    echo "   cp /home/wnstn4647/$BACKUP_NAME /mnt/d/backup/"
    echo ""
    echo "3. 새 PC에서 압축 해제:"
    echo "   tar -xzf $BACKUP_NAME"
    echo "   cd AI-CHAT"
    echo ""
    echo "4. 환경 설정:"
    echo "   python3 -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    echo ""
    echo "5. 테스트:"
    echo "   python3 test_system.py"
    echo "─────────────────────────────────────────"
    echo ""
    echo "✅ 이전 준비 완료!"

else
    echo "❌ 압축 실패"
    exit 1
fi
