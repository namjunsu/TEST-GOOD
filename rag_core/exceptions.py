"""
예외 처리 모듈
==============

RAG 시스템에서 발생할 수 있는 모든 예외를 정의합니다.
"""

import functools
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RAGException(Exception):
    """RAG 시스템 기본 예외 클래스"""
    pass


class DocumentNotFoundException(RAGException):
    """문서를 찾을 수 없을 때 발생"""
    pass


class PDFExtractionException(RAGException):
    """PDF 텍스트 추출 실패 시 발생"""
    pass


class LLMException(RAGException):
    """LLM 관련 오류 발생 시"""
    pass


class CacheException(RAGException):
    """캐시 관련 오류 발생 시"""
    pass


class SearchException(RAGException):
    """검색 관련 오류 발생 시"""
    pass


class ConfigException(RAGException):
    """설정 관련 오류 발생 시"""
    pass


def handle_errors(default_return: Optional[T] = None) -> Callable:
    """
    에러 처리 데코레이터

    Args:
        default_return: 에러 발생 시 반환할 기본값

    Returns:
        데코레이터 함수

    Example:
        ```python
        @handle_errors(default_return=[])
        def search_documents(query):
            # 검색 로직
            return results
        ```
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except RAGException as e:
                logger.error(f"{func.__name__} failed with RAG error: {e}")
                return default_return
            except Exception as e:
                logger.error(f"{func.__name__} failed with unexpected error: {e}")
                return default_return
        return wrapper
    return decorator