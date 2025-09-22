"""
Custom exceptions for RAG system
"""

class RAGException(Exception):
    """RAG 시스템 기본 예외"""
    pass

class DocumentNotFoundException(RAGException):
    """문서를 찾을 수 없을 때"""
    pass

class PDFExtractionException(RAGException):
    """PDF 추출 실패"""
    pass

class LLMException(RAGException):
    """LLM 관련 오류"""
    pass

class CacheException(RAGException):
    """캐시 관련 오류"""
    pass

class ValidationException(RAGException):
    """입력 검증 오류"""
    pass
