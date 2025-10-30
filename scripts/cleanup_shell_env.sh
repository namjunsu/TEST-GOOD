#!/usr/bin/env bash
# =============================================
# AI-CHAT 셸 환경변수 정리 스크립트
#
# 목적: 사용자 셸 초기화 파일에서 충돌 가능한
#       환경변수 설정을 제거하여 .env 권위화
# =============================================

set -euo pipefail

echo "=========================================="
echo "AI-CHAT 셸 환경변수 정리"
echo "=========================================="
echo ""

# 제거 대상 환경변수 패턴
PATTERNS=(
    '^export MODEL_PATH='
    '^export CHAT_FORMAT='
    '^export N_CTX='
    '^export N_GPU_LAYERS='
    '^export LLM_MODEL_PATH='
    '^export QWEN_MODEL_PATH='
)

# 정리 대상 파일
FILES=(
    "$HOME/.bashrc"
    "$HOME/.bash_profile"
    "$HOME/.profile"
    "$HOME/.zshrc"
)

CHANGED=false

for file in "${FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        continue
    fi

    echo "검사 중: $file"

    # 백업 생성
    if grep -qE "$(IFS='|'; echo "${PATTERNS[*]}")" "$file" 2>/dev/null; then
        backup="${file}.bak_$(date +%Y%m%d_%H%M%S)"
        cp "$file" "$backup"
        echo "  백업 생성: $backup"

        # 패턴 제거
        for pattern in "${PATTERNS[@]}"; do
            sed -i "/${pattern}/d" "$file"
        done

        echo "  ✅ 정리 완료"
        CHANGED=true
    else
        echo "  OK (변경 불필요)"
    fi
done

echo ""
echo "=========================================="

if $CHANGED; then
    echo "✅ 셸 환경변수 정리 완료"
    echo ""
    echo "변경 사항 적용을 위해 다음 중 하나를 실행하세요:"
    echo "  1) 새 터미널 열기"
    echo "  2) exec bash -l  (현재 쉘 재시작)"
    echo ""
    echo "확인:"
    echo "  printenv | grep -E '(MODEL_PATH|CHAT_FORMAT|N_CTX)' || echo '[OK] 환경변수 정리 확인'"
else
    echo "✅ 이미 정리되어 있습니다"
fi

echo "=========================================="
