"""RAG (Retrieval-Augmented Generation) Module

핵심 컴포넌트:
- pipeline: RAG 파사드 (단일 진입점)
- metrics: 성능 지표 수집
- retrievers: 검색 엔진들
"""

from app.rag.pipeline import RAGPipeline, RAGRequest, RAGResponse

__all__ = [
    "RAGPipeline",
    "RAGRequest",
    "RAGResponse",
]
