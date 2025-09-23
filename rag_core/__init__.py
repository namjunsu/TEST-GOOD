"""
RAG Core - 모듈화된 RAG 시스템
================================

이 패키지는 PerfectRAG를 기능별로 분리한 모듈들을 포함합니다.

모듈 구조:
- search/: 검색 관련 기능 (BM25, Vector, Hybrid)
- document/: 문서 처리 (PDF, 메타데이터, OCR)
- cache/: 캐싱 시스템 (LRU, Response Cache)
- llm/: LLM 관련 기능 (Qwen, Response Generation)
- utils/: 유틸리티 함수들

"""

__version__ = "2.0.0"
__author__ = "Channel A AI Team"

from .exceptions import *
from .config import RAGConfig