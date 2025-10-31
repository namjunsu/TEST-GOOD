# AI-CHAT System Overview

## Purpose

AI-CHAT is a document retrieval and question-answering system built on RAG (Retrieval-Augmented Generation) architecture. It enables semantic search and intelligent responses across Korean business documents, specifically optimized for broadcast equipment management documentation.

## Core Components

### 1. User Interface Layer
- **Streamlit Web UI** (`web_interface.py`): Main user interface on port 8501
- **FastAPI Backend** (`app/api/main.py`): REST API service on port 7860
- **Chat Interface**: Interactive Q&A with context retention

### 2. RAG Pipeline
- **Query Router**: Classifies queries into modes (LIST, SUMMARY, PREVIEW, QA, COST_SUM)
- **Retrieval System**: MetadataDB-based document search with filtering
- **Query Parser**: Closed-World Validation for entity extraction
- **Response Generator**: Currently simplified (LLM integration pending)

### 3. Data Layer
- **metadata.db**: SQLite database with document metadata (483 documents)
- **everything_index.db**: Full-text search index
- **Document Store**: PDF files organized by year in `docs/year_*/`

## Data Flow

```
User Query
    ↓
[Streamlit UI] → web_interface.py
    ↓
[Chat Interface] → components/chat_interface.py
    ↓
[RAG Pipeline] → app/rag/pipeline.py
    ├─ Query Router (mode classification)
    ├─ Query Parser (entity extraction)
    ├─ HybridRetriever (document search)
    └─ Response Generator
    ↓
Response Display
```

## Key Features

1. **Multi-Modal Query Support**
   - Natural language queries in Korean
   - Structured queries: `year:2024 drafter:최새름`
   - File name pattern matching

2. **Smart Filtering**
   - Year-based filtering
   - Drafter validation against database
   - Stopwords filtering for common nouns

3. **Response Types**
   - LIST: Document listings with metadata
   - SUMMARY: Content summaries
   - PREVIEW: Document previews
   - QA: Question answering
   - COST_SUM: Cost aggregation

## System Requirements

- Python 3.12+
- 2GB+ RAM
- 10GB disk space (for documents and indexes)
- Network ports: 8501 (UI), 7860 (API)

## Quick Start (10 minutes)

1. **Clone and Setup**
   ```bash
   git clone <repository>
   cd AI-CHAT
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start System**
   ```bash
   ./start_ai_chat.sh
   # Or manually:
   # make run
   ```

4. **Access UI**
   - Open browser: http://localhost:8501
   - API docs: http://localhost:7860/docs

## Current Status

### Working
- Document search and filtering
- Year/drafter extraction with validation
- List mode responses
- Basic chat interface

### Pending
- LLM integration for answer generation
- Vector search implementation
- Advanced reranking
- Full QA capabilities

## Architecture Highlights

- **Modular Design**: Clear separation of concerns
- **Database-Driven**: All metadata in SQLite for reliability
- **Extensible**: Plugin architecture for retrievers/generators
- **Cached Operations**: Known drafters cached for performance
- **Error Resilience**: Graceful degradation when components unavailable