"""RAG 핸들러 모듈

pipeline.py의 대규모 메서드들을 분리하여 관리.
점진적 마이그레이션을 위한 Strangler Fig 패턴 적용.

구조:
    handlers/
    ├── __init__.py
    ├── base.py          - 핸들러 기본 클래스
    ├── search.py        - 검색 핸들러 (SEARCH 모드)
    ├── document.py      - 문서 핸들러 (DOCUMENT 모드)
    └── response.py      - 응답 빌더

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
from .document import DocumentHandler
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
from .cost_sum import CostSumHandler
from .search import SearchHandler

__all__ = [
    # 핸들러 클래스
    "BaseHandler",
    "CostSumHandler",
    "DocumentHandler",
    "HandlerResponse",
    "SearchHandler",
    "build_empty_response",
    "build_error_response",
    # Evidence 빌더 함수
    "build_evidence_item",
    "build_evidence_list",
    "build_file_path",
    "build_standard_response",
    "clean_text_preview",
    # UI/텍스트 정리 함수
    "clean_ui_metadata",
    "encode_file_ref",
    "force_chat_mode",
    # 응답 포맷팅 함수
    "format_search_card",
    "format_search_results",
    # 파일/경로 함수
    "format_title_from_filename",
    # 키워드 분석 함수
    "get_keyword_coverage",
    "has_domain_keyword",
    "is_simple_math",
    # 쿼리 분류 함수
    "is_smalltalk",
    "normalize_chunk_text",
]
