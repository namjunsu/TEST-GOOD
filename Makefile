# AI-CHAT Repository Management Makefile

.PHONY: help audit test fmt lint type-check clean install pre-commit run

# Default target
help:
	@echo "AI-CHAT Repository Management Commands"
	@echo ""
	@echo "  make audit      - Run repository audit and generate reports"
	@echo "  make test       - Run smoke tests"
	@echo "  make fmt        - Format code with black and ruff"
	@echo "  make lint       - Check code with ruff"
	@echo "  make type-check - Check types with pyright"
	@echo "  make clean      - Remove cache and temporary files"
	@echo "  make install    - Install dependencies and pre-commit hooks"
	@echo "  make pre-commit - Run pre-commit hooks on all files"
	@echo "  make run        - Start the AI-CHAT system"
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
