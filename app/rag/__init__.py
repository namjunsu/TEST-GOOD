"""RAG (Retrieval-Augmented Generation) Module

핵심 컴포넌트:
- pipeline: RAG 파사드 (단일 진입점)
- contracts: 프로토콜/데이터클래스 정의
- query_routing: 쿼리 라우팅 로직
- adapters: 어댑터/폴백 클래스
- metrics: 성능 지표 수집
- retrievers: 검색 엔진들
"""

from app.rag.contracts import RAGRequest, RAGResponse, Retriever, Compressor, Generator
from app.rag.pipeline import RAGPipeline
from app.rag.query_routing import route_query, force_chat_mode

__all__ = [
    # 핵심 클래스
    "RAGPipeline",
    "RAGRequest",
    "RAGResponse",
    # 프로토콜
    "Retriever",
    "Compressor",
    "Generator",
    # 라우팅
    "route_query",
    "force_chat_mode",
]
