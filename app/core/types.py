"""공용 타입 정의

프로젝트 전반에서 재사용되는 타입 앨리어스 및 TypedDict 정의.
IDE 자동완성 및 타입 체킹 지원.

사용법:
    from app.core.types import DocumentDict, SearchResultDict, RAGResponseDict
"""

from enum import Enum
from typing import Any, NotRequired, Optional, TypedDict, Union

# ============================================================================
# 열거형 타입
# ============================================================================


class QuestionType(Enum):
    """질문 유형 (LLM 응답 생성용)"""
    SIMPLE = "simple"           # 단순 정보 조회
    COMPARISON = "comparison"   # 비교 질문
    ANALYSIS = "analysis"       # 분석 질문
    COMPLEX_MULTI = "complex_multi"  # 복합 다중 질문

# ============================================================================
# 문서 관련 타입
# ============================================================================


class DocumentMetadata(TypedDict):
    """문서 메타데이터"""
    filename: str
    title: NotRequired[str]
    date: NotRequired[str]
    year: NotRequired[int]
    category: NotRequired[str]
    drafter: NotRequired[str]
    keywords: NotRequired[str]
    path: NotRequired[str]
    page_count: NotRequired[int]
    file_size: NotRequired[int]


class DocumentDict(TypedDict):
    """문서 전체 정보"""
    id: NotRequired[int]
    filename: str
    content: str
    metadata: DocumentMetadata
    score: NotRequired[float]


# ============================================================================
# 검색 관련 타입
# ============================================================================

class SearchResultDict(TypedDict):
    """검색 결과 단일 항목"""
    filename: str
    content: str
    score: float
    metadata: DocumentMetadata
    source: NotRequired[str]  # "bm25" | "vector" | "hybrid"


class SearchResponseDict(TypedDict):
    """검색 응답 전체"""
    results: list[SearchResultDict]
    total_count: int
    query: str
    took_ms: NotRequired[float]


# ============================================================================
# RAG 파이프라인 타입
# ============================================================================

class RAGResponseDict(TypedDict):
    """RAG 응답"""
    mode: str  # "QA" | "SEARCH" | "DOCUMENT" | "COST_SUM" | "CHAT"
    text: str
    files: list[str]
    count: int
    citations: NotRequired[list[dict[str, Any]]]
    evidence: NotRequired[list[dict[str, Any]]]
    status: NotRequired[dict[str, Any]]
    latency_ms: NotRequired[float]


class QueryRoutingDict(TypedDict):
    """쿼리 라우팅 결과"""
    mode: str
    prompt_type: str
    max_tokens: int
    retriever_params: dict[str, Any]
    detailed_mode: bool
    detected_section: Optional[str]
    needs_summary: bool


# ============================================================================
# 캐시 관련 타입
# ============================================================================

class CacheStatsDict(TypedDict):
    """캐시 통계"""
    hits: int
    misses: int
    size: int
    max_size: int
    hit_rate: float


# ============================================================================
# 메트릭 관련 타입
# ============================================================================

class LatencyMetrics(TypedDict):
    """지연 시간 메트릭"""
    retrieve_ms: float
    compress_ms: NotRequired[float]
    generate_ms: NotRequired[float]
    total_ms: float


class SearchMetrics(TypedDict):
    """검색 메트릭"""
    query: str
    top_k: int
    result_count: int
    top_score: float
    latency: LatencyMetrics


# ============================================================================
# 타입 앨리어스
# ============================================================================

# JSON 호환 타입
JSONValue = Union[str, int, float, bool, None, dict[str, Any], list[Any]]
JSONDict = dict[str, JSONValue]

# 콜백 타입
ProgressCallback = Optional[callable]  # (current: int, total: int) -> None

# 검색 결과 리스트
SearchResults = list[SearchResultDict]
Documents = list[DocumentDict]


__all__ = [
    # 캐시
    "CacheStatsDict",
    "DocumentDict",
    # 문서
    "DocumentMetadata",
    "Documents",
    "JSONDict",
    # 앨리어스
    "JSONValue",
    # 메트릭
    "LatencyMetrics",
    "ProgressCallback",
    "QueryRoutingDict",
    # 열거형
    "QuestionType",
    # RAG
    "RAGResponseDict",
    "SearchMetrics",
    "SearchResponseDict",
    # 검색
    "SearchResultDict",
    "SearchResults",
]
