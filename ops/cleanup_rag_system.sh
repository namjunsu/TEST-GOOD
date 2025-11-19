#!/usr/bin/env bash
#
# RAG System 폴더 정리 스크립트
# rag_system/ → active/ (사용 중) / legacy/ (폐기 예정) 분리
#
# 사용법:
#   bash ops/cleanup_rag_system.sh           # 실행
#   bash ops/cleanup_rag_system.sh --dry-run # 시뮬레이션만
#

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

echo "================================================================================"
echo "                    RAG System 폴더 정리 (active/legacy 분리)"
echo "================================================================================"
echo "프로젝트 루트: $PROJECT_ROOT"
echo ""

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
    echo "🔍 DRY-RUN 모드: 실제 변경 없이 시뮬레이션만 수행합니다."
    echo ""
fi

# 계속 사용 중인 모듈 (삭제 불가)
ACTIVE_MODULES=(
    "bm25_store.py"
    "llm_wrapper.py"
    "llm_singleton.py"
    "enhanced_ocr_processor.py"
)

# 레거시 모듈 (삭제 후보)
LEGACY_MODULES=(
    "korean_vector_store.py"
    "hybrid_search.py"
    "korean_reranker.py"
    "document_compression.py"
    "query_expansion.py"
    "query_optimizer.py"
    "multilevel_filter.py"
    "metadata_extractor.py"
)

# 데이터/로그 파일
DATA_FILES=(
    "file_index.json"
    "file_index.json.backup_20251029_151046"
)

echo "=== 정리 계획 ==="
echo ""
echo "📦 Active 모듈 (유지):"
for module in "${ACTIVE_MODULES[@]}"; do
    echo "   ✓ $module"
done
echo ""

echo "🗂️  Legacy 모듈 (폐기 예정):"
for module in "${LEGACY_MODULES[@]}"; do
    echo "   → $module"
done
echo ""

echo "📊 데이터 파일:"
for file in "${DATA_FILES[@]}"; do
    if [ -f "rag_system/$file" ]; then
        SIZE=$(du -h "rag_system/$file" | cut -f1)
        echo "   • $file ($SIZE)"
    fi
done
echo ""

LOGS_SIZE=$(du -sh rag_system/logs 2>/dev/null | cut -f1 || echo "0")
echo "📝 로그 폴더: rag_system/logs ($LOGS_SIZE)"
echo ""

# 사용자 확인 (dry-run이 아닐 때만)
if [ "$DRY_RUN" = false ]; then
    read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 작업이 취소되었습니다."
        exit 0
    fi
fi

echo ""
echo "=== 폴더 구조 생성 ==="

# active 폴더 생성
if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] mkdir -p rag_system/active"
else
    mkdir -p rag_system/active
    echo "✓ rag_system/active/ 생성"
fi

# legacy 폴더 생성
if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] mkdir -p rag_system/legacy"
else
    mkdir -p rag_system/legacy
    echo "✓ rag_system/legacy/ 생성"
fi

echo ""
echo "=== Active 모듈 이동 ==="

for module in "${ACTIVE_MODULES[@]}"; do
    if [ -f "rag_system/$module" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] mv rag_system/$module → rag_system/active/"
        else
            mv "rag_system/$module" "rag_system/active/"
            echo "✓ $module → active/"
        fi
    else
        echo "⚠️  $module 파일 없음 (스킵)"
    fi
done

echo ""
echo "=== Legacy 모듈 이동 ==="

for module in "${LEGACY_MODULES[@]}"; do
    if [ -f "rag_system/$module" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] mv rag_system/$module → rag_system/legacy/"
        else
            mv "rag_system/$module" "rag_system/legacy/"
            echo "✓ $module → legacy/"
        fi
    else
        echo "⚠️  $module 파일 없음 (스킵)"
    fi
done

echo ""
echo "=== 데이터 파일 이동 (legacy) ==="

for file in "${DATA_FILES[@]}"; do
    if [ -f "rag_system/$file" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] mv rag_system/$file → rag_system/legacy/"
        else
            mv "rag_system/$file" "rag_system/legacy/"
            echo "✓ $file → legacy/"
        fi
    fi
done

echo ""
echo "=== __init__.py 생성 ==="

# active/__init__.py
if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] rag_system/active/__init__.py 생성"
else
    cat > rag_system/active/__init__.py << 'EOF'
"""
RAG System Active Modules
현재 사용 중인 핵심 모듈만 포함
"""
__version__ = "1.0.0"
EOF
    echo "✓ rag_system/active/__init__.py 생성"
fi

# legacy/__init__.py
if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] rag_system/legacy/__init__.py 생성"
else
    cat > rag_system/legacy/__init__.py << 'EOF'
"""
RAG System Legacy Modules
폐기 예정 - 30일 후 삭제 예정

DEPRECATED: 이 폴더의 모듈들은 더 이상 사용되지 않습니다.
app/rag/ 아키텍처로 대체되었습니다.
"""
__version__ = "0.9.0-deprecated"
EOF
    echo "✓ rag_system/legacy/__init__.py 생성"
fi

echo ""
echo "=== README 생성 ==="

if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] rag_system/legacy/README.md 생성"
else
    cat > rag_system/legacy/README.md << 'EOF'
# Legacy RAG Modules (DEPRECATED)

⚠️ **이 폴더는 폐기 예정입니다.**

## 상태
- **생성일**: $(date +%Y-%m-%d)
- **삭제 예정일**: $(date -d "+30 days" +%Y-%m-%d)
- **대체 구조**: `app/rag/`

## 포함된 모듈
모든 모듈은 `app/rag/` 아키텍처로 대체되었습니다:

| 레거시 모듈 | 대체 모듈 |
|------------|----------|
| korean_vector_store.py | (사용 안함, BM25로 대체) |
| hybrid_search.py | app/rag/retrievers/hybrid.py |
| korean_reranker.py | app/rag/reranker.py |
| query_expansion.py | app/rag/query_expander.py |
| metadata_extractor.py | modules/metadata_extractor.py |

## 삭제 절차
1. 30일간 운영 모니터링
2. 문제 없으면 전체 삭제: `rm -rf rag_system/legacy/`
EOF
    echo "✓ rag_system/legacy/README.md 생성"
fi

echo ""
echo "================================================================================"
echo "                              ✓ 정리 완료"
echo "================================================================================"
echo ""

if [ "$DRY_RUN" = false ]; then
    echo "📁 결과 구조:"
    echo "   rag_system/"
    echo "   ├── active/          # 사용 중 (4개 모듈)"
    echo "   │   ├── bm25_store.py"
    echo "   │   ├── llm_wrapper.py"
    echo "   │   ├── llm_singleton.py"
    echo "   │   └── enhanced_ocr_processor.py"
    echo "   ├── legacy/          # 폐기 예정 (30일 후 삭제)"
    echo "   │   ├── README.md"
    echo "   │   └── ..."
    echo "   ├── logs/            # 로그 (수동 정리 필요)"
    echo "   ├── db/"
    echo "   ├── cache/"
    echo "   └── __init__.py"
    echo ""
    echo "⚠️  다음 단계:"
    echo "   1. import 경로 수정: rag_system.xxx → rag_system.active.xxx"
    echo "   2. 테스트 실행: pytest tests/"
    echo "   3. 서비스 재시작 후 모니터링"
    echo "   4. 30일 후 legacy 폴더 삭제: rm -rf rag_system/legacy/"
    echo ""
    echo "📝 로그 정리 (선택):"
    echo "   rag_system/logs/ 폴더는 $LOGS_SIZE 사용 중입니다."
    echo "   필요시 수동 정리: rm -rf rag_system/logs/*"
else
    echo "✓ DRY-RUN 완료: 실제 변경은 없었습니다."
    echo "  실제 실행: bash ops/cleanup_rag_system.sh"
fi

echo ""
echo "================================================================================"

exit 0
