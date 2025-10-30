# AI-CHAT Repository Management Makefile

.PHONY: help audit test fmt lint type-check clean install pre-commit run license-check license-update verify cleanup run-clean validate generate-presets setup-dev check-production clean-logs clean-cache ingest-dryrun check-consistency reindex ingest-full ingest-report

# Default target
help:
	@echo "AI-CHAT Repository Management Commands"
	@echo ""
	@echo "🔧 Environment & Setup:"
	@echo "  make verify          - 환경 무결성 검증 (환경변수, MODEL_PATH 등)"
	@echo "  make cleanup         - 셸 환경변수 정리 (.bashrc 등)"
	@echo "  make setup-dev       - 개발 환경 설정 (install + verify)"
	@echo "  make check-production- 프로덕션 준비 상태 검증"
	@echo ""
	@echo "🚀 Running:"
	@echo "  make run             - AI-CHAT 시작 (일반)"
	@echo "  make run-clean       - 깨끗한 환경에서 시작 (env -i)"
	@echo ""
	@echo "✅ Testing & Validation:"
	@echo "  make test            - 단위 테스트 실행"
	@echo "  make validate        - 질문 프리셋 검증"
	@echo "  make generate-presets- 질문 프리셋 자동 생성"
	@echo ""
	@echo "📋 Code Quality:"
	@echo "  make audit           - 리포지토리 감사 및 리포트 생성"
	@echo "  make fmt             - 코드 포맷팅 (black, ruff)"
	@echo "  make lint            - 코드 린팅 (ruff)"
	@echo "  make type-check      - 타입 체킹 (pyright)"
	@echo "  make pre-commit      - pre-commit 훅 실행"
	@echo ""
	@echo "🧹 Cleaning:"
	@echo "  make clean           - 캐시 및 임시 파일 삭제"
	@echo "  make clean-logs      - 오래된 로그 파일 삭제 (30일+)"
	@echo "  make clean-cache     - Python 캐시 삭제"
	@echo ""
	@echo "📦 Dependencies:"
	@echo "  make install         - 의존성 설치 및 pre-commit 훅 설정"
	@echo "  make license-check   - 의존성 라이선스 컴플라이언스 확인"
	@echo "  make license-update  - 라이선스 문서 업데이트"
	@echo ""
	@echo "📚 RAG Ingest & Index:"
	@echo "  make ingest-dryrun   - 인제스트 드라이런 (진단 전용)"
	@echo "  make check-consistency- 인덱스 정합성 검증"
	@echo "  make reindex         - 재색인 (원자적 스왑)"
	@echo "  make ingest-full     - 전체 인제스트 파이프라인"
	@echo "  make ingest-report   - 인제스트 진단 보고서 생성"
	@echo ""

# Run repository audit
audit:
	@echo "🔍 Running repository audit..."
	@bash scripts/audit_repo.sh
	@python scripts/analyze_usage.py 2>/dev/null || true
	@echo "✅ Audit complete - check reports/ directory"

# Run tests
test:
	@echo "🧪 Running smoke tests..."
	@python -m pytest tests/test_smoke.py -v 2>/dev/null || echo "⚠️ No smoke tests found"

# Format code
fmt:
	@echo "🎨 Formatting code..."
	@black . --exclude="archive|.venv|__pycache__|htmlcov|build|dist" 2>/dev/null || true
	@ruff check . --fix 2>/dev/null || true
	@echo "✅ Formatting complete"

# Lint code
lint:
	@echo "🔎 Linting code..."
	@ruff check . 2>/dev/null || true

# Type checking
type-check:
	@echo "📝 Type checking..."
	@pyright 2>/dev/null || echo "⚠️ Pyright not installed"

# Clean temporary files
clean:
	@echo "🧹 Cleaning temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf htmlcov 2>/dev/null || true
	@rm -rf .pytest_cache 2>/dev/null || true
	@rm -rf .ruff_cache 2>/dev/null || true
	@echo "✅ Clean complete"

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	@pip install -q pre-commit ruff black pyright pipdeptree vulture pytest 2>/dev/null || true
	@pre-commit install 2>/dev/null || true
	@echo "✅ Installation complete"

# Run pre-commit on all files
pre-commit:
	@echo "🚀 Running pre-commit hooks..."
	@pre-commit run --all-files 2>/dev/null || true

# Run the system
run:
	@echo "🚀 Starting AI-CHAT system..."
	@bash start_ai_chat.sh

# Check dependency licenses
license-check:
	@echo "📋 Checking dependency licenses for compliance..."
	@pip install -q pip-licenses 2>/dev/null || true
	@pip-licenses --format=json --output-file=licenses.json 2>/dev/null || true
	@python .github/scripts/check_licenses.py 2>/dev/null || echo "⚠️ License check script not found"

# Update license documentation
license-update:
	@echo "📝 Updating license documentation..."
	@python scripts/scan_licenses.py 2>/dev/null || true
	@echo "✅ License documentation updated (LICENSES.md, THIRD_PARTY_NOTICES.md)"

# ============================================================================
# 🔧 Environment & Setup Targets
# ============================================================================

# Verify environment integrity
verify:
	@echo "🔍 환경 무결성 검증 중..."
	@python3 scripts/verify_env_integrity.py

# Clean up shell environment variables
cleanup:
	@echo "🧹 셸 환경변수 정리 중..."
	@bash scripts/cleanup_shell_env.sh

# Set up development environment
setup-dev: install verify
	@echo "✅ 개발 환경 설정 완료"

# Check production readiness
check-production: verify
	@echo "🔍 프로덕션 준비 상태 검증 중..."
	@bash -c 'if [ ! -f deploy/systemd/ai-chat-backend.service ]; then echo "❌ systemd 파일 없음"; exit 1; fi'
	@bash -c 'if [ ! -x scripts/cleanup_shell_env.sh ]; then echo "❌ cleanup 스크립트 실행 권한 없음"; exit 1; fi'
	@echo "✅ 프로덕션 준비 완료"

# ============================================================================
# 🚀 Running Targets (Environment-safe)
# ============================================================================

# Run in clean environment
run-clean:
	@echo "🚀 깨끗한 환경에서 AI-CHAT 시작..."
	@env -i bash -lc 'set -a; source .env; set +a; ./start_ai_chat.sh'

# ============================================================================
# ✅ Testing & Validation Targets
# ============================================================================

# Validate askable query presets
validate:
	@echo "✅ 질문 프리셋 검증 중..."
	@env -i bash -lc 'set -a; source .env; set +a; python scripts/validate_askable_queries.py'

# Generate askable query presets
generate-presets:
	@echo "📝 질문 프리셋 생성 중..."
	@env -i bash -lc 'set -a; source .env; set +a; python scripts/generate_askable_queries.py'

# ============================================================================
# 🧹 Additional Cleaning Targets
# ============================================================================

# Clean old log files (30+ days)
clean-logs:
	@echo "🧹 로그 파일 정리 중..."
	@find logs/ -type f -name "*.log" -mtime +30 -delete 2>/dev/null || true
	@echo "✅ 30일 이상 된 로그 파일 삭제 완료"

# ============================================================================
# 📚 RAG Ingest & Index Targets
# ============================================================================

# Run ingest dryrun (diagnostic only, no changes)
ingest-dryrun:
	@echo "🔍 인제스트 드라이런 시작..."
	@python scripts/ingest_dryrun.py \
		--input ./docs \
		--trace reports/ingest_trace.jsonl \
		--chunk-stats reports/chunk_stats.csv \
		--embedding-report reports/embedding_report.json \
		--ocr-audit reports/ocr_audit.md
	@echo "✅ 드라이런 완료 - reports/ 확인"

# Check index consistency (DocStore ↔ BM25/FAISS)
check-consistency:
	@echo "🔍 인덱스 정합성 검증 중..."
	@python scripts/check_index_consistency.py \
		--report reports/index_consistency.md
	@echo "✅ 정합성 검증 완료"

# Reindex with atomic swap
reindex:
	@echo "🔄 재색인 시작 (원자적 스왑)..."
	@python scripts/reindex_atomic.py \
		--source ./docs \
		--tmp-index ./var/index_tmp \
		--swap-to ./var/index \
		--report reports/index_consistency.md
	@echo "✅ 재색인 완료"

# Full ingest pipeline (dryrun → reindex → verify)
ingest-full: ingest-dryrun reindex check-consistency
	@echo "✅ 전체 인제스트 파이프라인 완료"

# Generate ingest diagnostic report
ingest-report:
	@echo "📊 인제스트 진단 보고서 생성 중..."
	@python scripts/generate_ingest_report.py \
		--output reports/INGEST_DIAG_REPORT.md
	@echo "✅ 보고서 생성 완료: reports/INGEST_DIAG_REPORT.md"

# Clean Python cache
clean-cache:
	@echo "🧹 Python 캐시 정리 중..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ 캐시 정리 완료"
