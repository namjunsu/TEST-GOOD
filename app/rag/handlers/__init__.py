"""RAG 핸들러 모듈

pipeline.py의 대규모 메서드들을 분리하여 관리.
점진적 마이그레이션을 위한 Strangler Fig 패턴 적용.

구조:
    handlers/
    ├── __init__.py
    ├── base.py              - 핸들러 기본 클래스
    ├── search.py            - 검색 핸들러 (SEARCH 모드)
    ├── document.py          - 문서 핸들러 (DOCUMENT 모드)
    ├── response.py          - 응답 빌더
    ├── query_processor.py   - 쿼리 정제/필터 추출 (2025-12-22)
    └── result_formatter.py  - 결과 포맷팅 (2025-12-22)

사용법 (점진적 마이그레이션):
    # pipeline.py에서
    from app.rag.handlers import SearchHandler

    class RAGPipeline:
        def __init__(self):
            self._search_handler = SearchHandler(self)

        def _answer_search(self, query):
            return self._search_handler.handle(query)
"""

from .base import BaseHandler, HandlerResponse
from .cost_sum import CostSumHandler
from .document import DocumentHandler
from .query_processor import (
    CONTENT_STOP_WORDS,
    STOP_WORDS,
    calculate_max_docs,
    extract_drafter_filter,
    extract_keywords,
    extract_year_filter,
    is_count_query,
    is_list_query,
    needs_expanded_search,
)
from .response import (
    build_empty_response,
    build_error_response,
    # Evidence 빌더
    build_evidence_item,
    build_evidence_list,
    build_file_path,
    build_standard_response,
    clean_text_preview,
    # UI/텍스트 정리
    clean_ui_metadata,
    encode_file_ref,
    force_chat_mode,
    # 응답 포맷팅
    format_search_card,
    format_search_results,
    # 파일/경로
    format_title_from_filename,
    # 키워드 분석
    get_keyword_coverage,
    has_domain_keyword,
    is_simple_math,
    # 쿼리 분류
    is_smalltalk,
    normalize_chunk_text,
)
from .result_formatter import EMPTY_VALUES, ResultFormatter
from .search import SearchHandler

__all__ = [
    # 핸들러 클래스
    "BaseHandler",
    "CostSumHandler",
    "DocumentHandler",
    "HandlerResponse",
    "ResultFormatter",
    "SearchHandler",
    # 쿼리 처리 함수 (query_processor.py)
    "CONTENT_STOP_WORDS",
    "EMPTY_VALUES",
    "STOP_WORDS",
    "calculate_max_docs",
    "extract_drafter_filter",
    "extract_keywords",
    "extract_year_filter",
    "is_count_query",
    "is_list_query",
    "needs_expanded_search",
    # 응답 빌더 함수
    "build_empty_response",
    "build_error_response",
    "build_evidence_item",
    "build_evidence_list",
    "build_file_path",
    "build_standard_response",
    "clean_text_preview",
    "clean_ui_metadata",
    "encode_file_ref",
    "force_chat_mode",
    "format_search_card",
    "format_search_results",
    "format_title_from_filename",
    "get_keyword_coverage",
    "has_domain_keyword",
    "is_simple_math",
    "is_smalltalk",
    "normalize_chunk_text",
]
