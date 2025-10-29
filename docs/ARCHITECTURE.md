# AI-CHAT Architecture

## Component Architecture

```
┌──────────────────────────────────────────────────────┐
│                   User Interface                      │
├────────────────┬──────────────────────────────────────┤
│  Streamlit UI  │          FastAPI Backend             │
│  (Port 8501)   │          (Port 7860)                 │
└────────┬───────┴──────────────┬───────────────────────┘
         │                      │
         ▼                      ▼
┌────────────────────────────────────────────────────────┐
│                    RAG Pipeline                         │
├──────────────┬─────────────┬─────────────┬────────────┤
│ Query Router │ Query Parser│  Retriever  │ Generator  │
└──────────────┴──────┬──────┴──────┬──────┴────────────┘
                      │              │
                      ▼              ▼
         ┌─────────────────────────────────────┐
         │         Data Layer                  │
         ├──────────────┬──────────────────────┤
         │ metadata.db  │ everything_index.db  │
         │   (SQLite)   │    (FTS Index)       │
         └──────────────┴──────────────────────┘
```

## Module Dependencies

### Core Modules

1. **app/rag/pipeline.py**
   - Central orchestrator for RAG operations
   - Dependencies:
     - `app/rag/query_router.py`: Query classification
     - `app/rag/query_parser.py`: Entity extraction
     - `app/rag/retrievers/hybrid.py`: Document retrieval
     - `modules/metadata_db.py`: Database operations

2. **app/rag/query_router.py**
   - Classifies queries into operational modes
   - Config: `config/document_processing.yaml`
   - Returns: QueryMode enum (LIST, SUMMARY, PREVIEW, QA, COST_SUM)

3. **app/rag/query_parser.py**
   - Extracts entities with Closed-World Validation
   - Config: `config/filters.yaml`
   - Features:
     - Token syntax parsing (year:2024)
     - Fuzzy matching (threshold: 0.85)
     - Stopwords filtering

4. **modules/metadata_db.py**
   - Database interface layer
   - Operations:
     - `search_documents()`: Multi-filter search
     - `list_unique_drafters()`: Closed-world set
     - `get_document_by_filename()`: Direct lookup

### UI Components

1. **components/chat_interface.py**
   - Chat session management
   - Message history
   - Context expansion for follow-up questions

2. **components/sidebar_library.py**
   - Document browser
   - Filter controls
   - Statistics display

3. **components/document_preview.py**
   - PDF rendering
   - Metadata display
   - Navigation controls

## Configuration Schema

### Environment Variables (.env)
```bash
AI_CHAT_PORT=8501
AI_CHAT_HOST=0.0.0.0
AI_CHAT_VENV=.venv
LLM_ENABLED=false
OPENAI_API_KEY=<optional>
```

### Config Files

1. **config/filters.yaml**
   ```yaml
   drafter_stopwords:
     - 문서
     - 자료
     - 보고서
   query_tokens:
     year: "year:\\s*(\\d{4})"
     drafter: "drafter:\\s*([가-힣]+)"
   ```

2. **config/document_processing.yaml**
   ```yaml
   qa_keywords: []
   preview_keywords: []
   list_keywords: [목록, 리스트, 찾아]
   ```

## Data Flow Patterns

### Query Processing Flow
```
Query Input
    ↓
Query Router (Mode Classification)
    ↓
Query Parser (Entity Extraction)
    ├─ Token Parsing
    ├─ Year Extraction
    └─ Drafter Validation
    ↓
Mode-Specific Handler
    ├─ LIST → _answer_list()
    ├─ SUMMARY → _answer_summary()
    ├─ PREVIEW → _answer_preview()
    ├─ QA → Pattern matching + Retrieval
    └─ COST_SUM → _answer_cost_sum()
    ↓
Response Generation
```

### Retrieval Flow
```
Search Request
    ↓
HybridRetriever.search()
    ↓
MetadataDB.search_documents()
    ├─ Year Filter (SQL WHERE)
    ├─ Drafter Filter (SQL LIKE)
    └─ Limit Application
    ↓
Result Normalization
    ├─ Score Assignment
    ├─ Snippet Extraction
    └─ Metadata Enrichment
    ↓
Response Formatting
```

## Database Schema

### metadata.db Tables

1. **documents**
   ```sql
   CREATE TABLE documents (
       id INTEGER PRIMARY KEY,
       filename TEXT UNIQUE,
       drafter TEXT,
       date TEXT,
       display_date TEXT,
       doctype TEXT,
       text_preview TEXT,
       category TEXT DEFAULT 'pdf'
   );
   ```

2. **documents_fts**
   ```sql
   CREATE VIRTUAL TABLE documents_fts USING fts5(
       filename, drafter, text_preview,
       content=documents
   );
   ```

## Error Handling Strategy

1. **Graceful Degradation**
   - Missing LLM → Return search results only
   - Database error → Fallback to file system
   - Network timeout → Cached responses

2. **Error Codes**
   - E_RETRIEVAL: Search failures
   - E_GENERATE: Generation failures
   - E_PARSE: Query parsing errors
   - E_DB: Database errors

3. **Logging Levels**
   - INFO: Normal operations
   - WARNING: Degraded functionality
   - ERROR: Component failures
   - DEBUG: Detailed diagnostics

## Performance Considerations

1. **Caching**
   - Known drafters cached on startup
   - Query router config cached
   - Database connections pooled

2. **Indexing**
   - SQLite FTS5 for full-text search
   - Filename index for direct lookups
   - Date index for range queries

3. **Optimization Points**
   - Batch database operations
   - Lazy loading for large documents
   - Response streaming for UI

## Extension Points

1. **Custom Retrievers**
   - Implement retriever protocol
   - Add to pipeline configuration
   - Examples: VectorRetriever, ElasticRetriever

2. **Custom Generators**
   - Implement generator protocol
   - Support for different LLMs
   - Examples: OpenAIGenerator, ClaudeGenerator

3. **Custom Query Modes**
   - Extend QueryMode enum
   - Add handler method
   - Update router configuration

## Security Considerations

1. **Input Validation**
   - SQL injection prevention (parameterized queries)
   - Path traversal prevention
   - Query length limits

2. **Authentication**
   - Currently none (internal use)
   - Extension point for OAuth/JWT

3. **Data Protection**
   - Local database only
   - No external API calls (when LLM disabled)
   - File access restricted to docs/ directory