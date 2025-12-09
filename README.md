# AI-CHAT: Document Retrieval & QA System

> Intelligent document search and question-answering system with RAG architecture

## 🚀 Quick Start (10 minutes)

### Prerequisites
- Python 3.12+
- 2GB+ RAM
- 10GB disk space

### Installation

```bash
# 1. Clone repository
git clone <repository-url>
cd AI-CHAT

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings
```

### Run the System

```bash
# Method 1: Using launcher script (recommended)
./start_ai_chat.sh

# Method 2: Using Makefile
make run

# Method 3: Manual start
source .venv/bin/activate
uvicorn app.api.main:app --port 7860 &
streamlit run web_interface.py --port 8501
```

### Access the Application
- **Web UI**: http://localhost:8501
- **API Docs**: http://localhost:7860/docs
- **Health Check**: http://localhost:7860/_healthz

## 📊 System Information

- **Documents**: 475 PDFs indexed (2014-2025)
- **Database**: SQLite with WAL mode
- **Architecture**: RAG (Retrieval-Augmented Generation)
- **Language**: Korean document support with OCR
- **Python**: 3.11+
- **Files**: 43 MD, 14 SH, 207 PY
- **Last Updated**: 2025-12-09

## 🎯 Query Modes

The system supports multiple query modes with automatic routing:

### SEARCH Mode
Find documents by keyword or topic.

**Examples:**
- "중계차 카메라 렌즈관련 문서 찾아줘"
- "유인혁 기안서 문서 검색"
- "렌즈 오버홀 문서 있어?"

**Features:**
- BM25 keyword-based retrieval
- Metadata enrichment (author, date, cost)
- Card-style results with preview

### SUMMARY Mode
Get detailed summaries of specific documents.

**Examples:**
- "2024-03-15_중계차_렌즈_오버홀.pdf 내용 요약해줘"
- "이 문서 요약해줘" (with document selected)

**Features:**
- Document type detection (기안서, 검토서, etc.)
- JSON-structured extraction
- Spec details and cost information

### QA Mode
Ask specific questions about documents.

**Examples:**
- "렌즈 오버홀 비용은 얼마였어?"
- "유인혁이 작성한 문서의 주요 내용은?"

**Features:**
- Retrieval-augmented generation
- Context-aware answers
- Source citations

### LIST Mode
Browse documents by author or year.

**Examples:**
- "2024년 남준수 문서 전부"
- "year:2024 drafter:최새름"

**Features:**
- Structured metadata filtering
- Chronological sorting
- Compact 2-line cards

### COST_SUM Mode
Get cost aggregates from documents.

**Examples:**
- "채널에이 중계차 보수 합계는?"
- "2024년 총 비용"

**Features:**
- Direct DB aggregation
- Drafter/year filtering
- Fast numerical results

## 🛠️ Development

### Project Structure
```
AI-CHAT/
├── app/                    # Main application code
│   ├── api/                # REST API endpoints
│   ├── rag/                # RAG pipeline & retrievers
│   ├── prompts/            # AI prompts
│   └── utils/              # Utilities
├── config/                 # Configuration files (YAML)
├── docs/                   # Documentation
│   └── archive/            # Old reports (archived)
├── scripts/                # Maintenance & operation scripts
│   ├── core/               # Core functionality
│   ├── data/               # Data processing
│   │   ├── ocr/            # OCR processing
│   │   ├── metadata/       # Metadata processing
│   │   └── indexing/       # Index management
│   ├── validation/         # Testing & validation
│   ├── monitoring/         # Performance monitoring
│   └── ops/                # Operations (backup, health)
├── tests/                  # Test files
├── rag_system/             # RAG index & data
├── models/                 # ML models (6GB)
└── var/                    # Runtime files
```

### Common Commands

```bash
# Repository management
make audit          # Run code audit
make test           # Run smoke tests
make fmt            # Format code
make lint           # Lint code
make clean          # Clean cache files

# Development
make install        # Install dev dependencies
make pre-commit     # Run pre-commit hooks

# Troubleshooting
python health_check.py              # System health check
python diagnose_qa_flow.py          # Test QA flow
python scripts/analyze_usage.py     # Analyze code usage
```


## 📖 Documentation

### Core Documentation
- [System Overview](docs/SYSTEM_OVERVIEW.md) - Architecture and components
- [Architecture](docs/ARCHITECTURE.md) - Technical design and dependencies
- [Runbook](docs/RUNBOOK.md) - Operations and troubleshooting
- [Operations](docs/OPERATIONS.md) - Daily operations guide
- [RAG Implementation](docs/RAG_V2_IMPLEMENTATION.md) - RAG v2 details

### Additional Resources
- [ChatGPT Context](docs/CHATGPT_PROJECT_CONTEXT.md) - Full project context
- [Cache Usage](docs/CACHE-USAGE-v2.md) - Caching guide
- [Archived Docs](docs/archive/) - Historical reports

## 🔧 Troubleshooting

### Common Issues

**Port already in use**
```bash
lsof -i :8501  # Find process
kill -9 <PID>   # Kill process
```

**Database locked**
```bash
rm metadata.db-shm metadata.db-wal
sqlite3 metadata.db "PRAGMA integrity_check;"
```

**No search results**
```bash
python check_db_content.py
python rebuild_metadata.py
```

**config.py not found**
```bash
git restore config.py
# Or create minimal config
echo "DOCS_DIR = 'docs'" > config.py
```

See [Runbook](docs/RUNBOOK.md) for detailed troubleshooting.

## 🧪 Testing

Run smoke tests to verify system functionality:

```bash
# Quick smoke test
python tests/test_smoke.py

# Or using Make
make test
```

All tests should pass for a healthy system.

## 📝 Contributing

1. Create a feature branch
2. Make changes
3. Run tests and linting
4. Submit pull request

### Code Quality

Before committing:
```bash
make fmt        # Format code
make lint       # Check linting
make test       # Run tests
make pre-commit # Run all hooks
```

## 📊 System Status

- **Active Files**: 207 Python files (정리 완료)
- **Documentation**: 43 MD files (핵심 문서만 유지)
- **Scripts**: 14 SH files (중복 제거)
- **Test Coverage**: 8/8 smoke tests passing
- **Code Quality**: Ruff + Black + Pre-commit configured

## 🔒 Security

- Local database only (no external API calls)
- SQL injection prevention (parameterized queries)
- Path traversal prevention
- File access restricted to docs/ directory

## 📄 License

[License information here]

## 🤝 Support

- Check documentation in `docs/` folder
- Review recent commits: `git log --oneline -10`
- Create GitHub issue for bugs
- Contact system administrator for urgent issues

---

**Version**: 2025.12.09
**Status**: Production Ready
**Last Updated**: 2025-12-09
