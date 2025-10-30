# Changelog

## [2025-10-30] LLM Wrapper Generalization & Chat Format Auto-Detection

**Branch**: chore/repo-hygiene-20251029
**Impact**: Model compatibility, Code maintainability

### Summary

Generalized `qwen_llm.py` to `llm_wrapper.py` with automatic chat format detection, enabling seamless support for multiple LLM architectures (LLaMA, Qwen, etc.) without code changes.

### Key Changes

#### 1. File Renaming & Import Updates
- **Renamed**: `rag_system/qwen_llm.py` → `rag_system/llm_wrapper.py`
- **Updated imports** across all modules:
  - `rag_system/llm_singleton.py`
  - `experiments/hybrid_chat_rag_v2.py`
  - Test scripts: `test_qa_simple.py`, `test_model_direct.py`, etc.

#### 2. Chat Format Auto-Detection
- **New feature**: `CHAT_FORMAT` environment variable with `auto` default
  - `auto`: Uses GGUF metadata's `tokenizer.chat_template` (recommended)
  - Manual override: `llama-2`, `chatml`, `qwen`, `zephyr`, etc.

- **Implementation** (`llm_wrapper.py:107-116`):
  ```python
  chat_format_env = os.getenv('CHAT_FORMAT', 'auto').lower()
  if chat_format_env == 'auto':
      self.chat_format = None  # Uses GGUF metadata
  else:
      self.chat_format = chat_format_env  # Explicit override
  ```

#### 3. Enhanced Model Metadata Logging
- Logs now display at model load:
  - `📊 Model Architecture`: llama, qwen, etc.
  - `📊 Model Type`: LLaMA v2, Qwen2.5, etc.
  - `📊 Vocab Type`: tokenizer type
  - `💬 Chat Template`: auto-detected or overridden

#### 4. Environment Configuration
- **Added to `.env` and `.env.example`**:
  ```bash
  # Chat Format 설정
  # auto: GGUF 메타데이터의 tokenizer.chat_template 자동 사용 (권장)
  # 강제 지정: llama-2, chatml, qwen, zephyr 등
  CHAT_FORMAT=auto
  ```

#### 5. Test Coverage
- **New unit tests** (`tests/test_chat_format_auto.py`): 7/7 PASSED
  - Auto-detection validation
  - Manual override testing (llama-2, chatml, qwen)
  - Case-insensitive handling
  - Default behavior verification

#### 6. Model Migration Validated
- **Previous model**: Qwen 2.5-7B (4.4GB, 7B params)
- **New model**: LLaMA v2 GGML (6.07GB, 10.8B params, Q4_K_M quantization)
- **E2E test**: 4/4 Q&A scenarios passed
- **Performance**: ~25-28 tokens/sec on RTX 4060 GPU

### Migration Guide

#### For Developers
```bash
# Update imports in your code
- from rag_system.qwen_llm import QwenLLM
+ from rag_system.llm_wrapper import QwenLLM
```

#### For Operators
```bash
# Use auto-detection (recommended)
CHAT_FORMAT=auto

# Or force specific format for legacy models
CHAT_FORMAT=qwen  # For Qwen models
CHAT_FORMAT=llama-2  # For LLaMA models
```

### Benefits
1. **Model agnostic**: Supports any GGUF model with chat template metadata
2. **Zero-config**: Auto-detection works out-of-the-box
3. **Backward compatible**: Can force legacy formats if needed
4. **Better observability**: Detailed logging of detected formats
5. **Tested**: Unit tests + E2E validation with actual model

### References
- llama-cpp-python chat_format priority: `chat_handler > chat_format > GGUF metadata > fallback(llama-2)`
- GGUF metadata spec: [gguf-py](https://github.com/ggerganov/ggml/tree/master/docs)

---

## [2025-10-29] Repository Reorganization

Date: 2025-10-29 19:52
Branch: chore/repo-hygiene-20251029

## Summary

Reorganized repository structure to improve maintainability.
- No files deleted, only moved to archive
- No functionality changed
- Standard folder structure implemented

## Directory Structure Changes

### New Standard Structure
```
/
├─ apps/               # Entry points (Streamlit/FastAPI)
├─ src/                # Core library modules
│   ├─ rag/            # RAG pipeline components
│   ├─ io/             # Document loaders/parsers
│   ├─ config/         # Configuration schemas
│   ├─ components/     # UI components
│   ├─ modules/        # Core modules
│   └─ utils/          # Utilities
├─ configs/            # Configuration files
├─ scripts/            # Maintenance scripts
├─ tests/              # Test files
├─ docs/               # Documentation
├─ reports/            # Analysis reports
└─ archive/20251029/   # Archived unused files
```

## File Movement Summary

### Active Files Reorganized
- web_interface.py → apps/web_interface.py
- app/rag/* → src/rag/*
- app/config/* → src/config/*
- app/api/* → apps/api/*
- components/* → src/components/*
- modules/* → src/modules/*
- utils/* → src/utils/*
- config/* → configs/*

### Files Archived (Not Deleted)
- Total files archived: See archive/20251029/
- Categories: tests, experiments, scripts, legacy, utils, other

## Import Path Updates Required

After reorganization, update imports:
- `from app.rag` → `from src.rag`
- `from app.config` → `from src.config`
- `from components` → `from src.components`
- `from modules` → `from src.modules`
- `from utils` → `from src.utils`

## Next Steps

1. Update all import statements
2. Test system functionality
3. Update documentation
4. Remove old empty directories
