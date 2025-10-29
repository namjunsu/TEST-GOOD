# Execution Entrypoints Analysis

## Main Execution Scripts

### 1. Primary Script: `start_ai_chat.sh`
- **Status**: Active, executable (+x)
- **Purpose**: Main system launcher
- **Actions**:
  1. Activates Python virtual environment (.venv)
  2. Runs system checks (utils/system_checker.py)
  3. Starts FastAPI backend (port 7860): `uvicorn app.api.main:app`
  4. Starts Streamlit UI (port 8501): `streamlit run web_interface.py`
- **Environment Variables**:
  - AI_CHAT_PORT (default: 8501)
  - AI_CHAT_HOST (default: 0.0.0.0)
  - AI_CHAT_VENV (default: .venv)

### 2. Legacy Script: `run_rag.sh`
- **Status**: Deprecated (no execute permission)
- **References**: src/web_interface.py (non-existent path)
- **Action Required**: Move to archive

## Python Entry Points

### Primary
- `web_interface.py`: Streamlit UI main application
- `app/api/main.py`: FastAPI REST API server

### Utility Scripts
- `health_check.py`: System health verification
- `diagnose_qa_flow.py`: QA flow diagnostic tool
- `rebuild_metadata.py`: Database rebuilding
- `rebuild_rag_indexes.py`: Index recreation
- `fix_metadata_db.py`: Database repair
- `check_db_content.py`: Database content verification
- `everything_like_search.py`: Search testing
- `verify_golden_queries.py`: Query validation

### Test Scripts
- `test_e2e_validation.py`: End-to-end tests
- `test_final_validation.py`: Final validation tests
