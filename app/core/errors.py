"""애플리케이션 예외 정의

계층적 예외 구조:
- AppError (기본)
  - ConfigError (설정)
  - DatabaseError (데이터베이스)
  - ModelError (AI 모델)
  - SearchError (검색)
  - ValidationError (입력 검증)

FastAPI 연동:
    try:
        ...
    except Exception as e:
        raise SearchError("검색 실패", str(e), code=ErrorCode.E_RETRIEVE).to_http()

로깅 연동:
    try:
        ...
    except Exception as e:
        err = SearchError("검색 실패", str(e), code=ErrorCode.E_RETRIEVE)
        log_error(err)
        raise err
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict

# 표준 로거
logger = logging.getLogger("app.core.errors")


# ============================================================================
# 에러 코드 (Enum)
# ============================================================================

class ErrorCode(str, Enum):
    """RAG 파이프라인 에러 코드

    UI에서 에러 코드 기반 메시지 매핑에 사용.
    Enum으로 정의해 IDE 자동 완성 및 오타 방지.
    """
    # 검색 단계
    E_RETRIEVE = "E_RETRIEVE"  # 검색 실패
    E_INDEX_LOAD = "E_INDEX_LOAD"  # 인덱스 로드 실패
    E_INDEX_LOCK = "E_INDEX_LOCK"  # 인덱스 파일락 충돌

    # 재랭킹 단계
    E_RERANK = "E_RERANK"  # 재랭킹 실패

    # 압축 단계
    E_COMPRESS = "E_COMPRESS"  # 압축 실패

    # 생성 단계
    E_GENERATE = "E_GENERATE"  # LLM 생성 실패
    E_MODEL_LOAD = "E_MODEL_LOAD"  # 모델 로드 실패

    # 데이터베이스
    E_DB_BUSY = "E_DB_BUSY"  # DB 동시 접근 충돌
    E_DB_LOCK = "E_DB_LOCK"  # DB 락 타임아웃
    E_DB_CORRUPT = "E_DB_CORRUPT"  # DB 손상

    # 시스템
    E_TIMEOUT = "E_TIMEOUT"  # 타임아웃
    E_MEMORY = "E_MEMORY"  # 메모리 부족
    E_NETWORK = "E_NETWORK"  # 네트워크 오류


# UI 메시지 매핑
ERROR_MESSAGES = {
    ErrorCode.E_RETRIEVE: "🔍 검색 중 오류가 발생했습니다.",
    ErrorCode.E_INDEX_LOAD: "📚 인덱스를 불러올 수 없습니다. 재인덱싱이 필요합니다.",
    ErrorCode.E_INDEX_LOCK: "🔒 인덱스가 사용 중입니다. 잠시 후 다시 시도해주세요.",
    ErrorCode.E_RERANK: "🎯 결과 정렬 중 오류가 발생했습니다.",
    ErrorCode.E_COMPRESS: "📦 문서 압축 중 오류가 발생했습니다.",
    ErrorCode.E_GENERATE: "🤖 답변 생성 중 오류가 발생했습니다.",
    ErrorCode.E_MODEL_LOAD: "⚙️ AI 모델을 불러올 수 없습니다.",
    ErrorCode.E_DB_BUSY: "💾 데이터베이스가 사용 중입니다. 잠시 후 다시 시도해주세요.",
    ErrorCode.E_DB_LOCK: "🔒 데이터베이스 접근 시간 초과입니다.",
    ErrorCode.E_DB_CORRUPT: "⚠️ 데이터베이스 손상이 의심됩니다. 관리자에게 문의하세요.",
    ErrorCode.E_TIMEOUT: "⏱️ 응답 시간이 초과되었습니다. 다시 시도해주세요.",
    ErrorCode.E_MEMORY: "💾 메모리가 부족합니다. 대화 내역을 정리해주세요.",
    ErrorCode.E_NETWORK: "🌐 네트워크 오류가 발생했습니다.",
}


# ============================================================================
# 예외 클래스
# ============================================================================

class AppError(Exception):
    """애플리케이션 기본 예외

    Attributes:
        message: 사용자 친화적 메시지
        details: 기술적 상세 정보 (로깅용)
        code: ErrorCode Enum 값
        status_code: HTTP 응답 코드 (FastAPI 연동용)

    Example:
        raise AppError("처리 실패", details="stack trace...", code=ErrorCode.E_TIMEOUT, status_code=503)
    """

    def __init__(
        self,
        message: str,
        details: str | None = None,
        code: ErrorCode | None = None,
        status_code: int = 500
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.code = code
        self.status_code = status_code

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (상세: {self.details})"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """직렬화 가능한 딕셔너리로 변환 (로깅/API 응답용)"""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "code": self.code.value if self.code else None,
            "status_code": self.status_code,
        }

    def to_http(self):
        """FastAPI용 HTTPException 변환

        Returns:
            HTTPException: FastAPI가 처리 가능한 예외

        Example:
            raise SearchError("검색 실패", code=ErrorCode.E_RETRIEVE).to_http()
        """
        try:
            from fastapi import HTTPException
        except ImportError:
            raise ImportError("FastAPI가 설치되지 않았습니다. pip install fastapi") from None

        return HTTPException(
            status_code=self.status_code,
            detail={
                "error": self.code.value if self.code else self.__class__.__name__,
                "message": self.message,
                "details": self.details,
            },
        )


class ConfigError(AppError):
    """설정 관련 예외

    Example:
        raise ConfigError("설정 파일 로드 실패", details="/path/to/config.json", code=ErrorCode.E_TIMEOUT)
    """
    def __init__(self, message: str, details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code, status_code=500)


class DatabaseError(AppError):
    """데이터베이스 관련 예외

    Example:
        raise DatabaseError("DB 연결 실패", details="timeout after 5s", code=ErrorCode.E_DB_BUSY)
    """
    def __init__(self, message: str, details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code, status_code=503)


class ModelError(AppError):
    """AI 모델 관련 예외

    Example:
        raise ModelError("모델 로드 실패", details="CUDA out of memory", code=ErrorCode.E_MODEL_LOAD)
    """
    def __init__(self, message: str, details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code, status_code=503)


class SearchError(AppError):
    """검색 관련 예외

    Example:
        raise SearchError("인덱스 로드 실패", details="index file not found", code=ErrorCode.E_INDEX_LOAD)
    """
    def __init__(self, message: str, details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code, status_code=500)


class ValidationError(AppError):
    """입력 검증 실패

    Example:
        raise ValidationError("빈 질문", details="query cannot be empty")
    """
    def __init__(self, message: str, details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code, status_code=400)


class DocumentNotFoundError(SearchError):
    """문서를 찾을 수 없음

    Example:
        raise DocumentNotFoundError("문서 없음", details="filename=test.pdf")
    """
    def __init__(self, message: str = "요청한 문서를 찾을 수 없습니다", details: str | None = None):
        super().__init__(message, details, code=ErrorCode.E_RETRIEVE)
        self.status_code = 404


class OCRProcessingError(AppError):
    """OCR 처리 실패

    Example:
        raise OCRProcessingError("OCR 실패", details="PaddleOCR timeout")
    """
    def __init__(self, message: str = "OCR 처리 중 오류가 발생했습니다", details: str | None = None):
        super().__init__(message, details, code=None, status_code=500)


class CacheExpiredError(AppError):
    """캐시 만료

    Example:
        raise CacheExpiredError("캐시 만료", details="key=query_hash_123")
    """
    def __init__(self, message: str = "캐시가 만료되었습니다", details: str | None = None):
        super().__init__(message, details, code=None, status_code=410)


class IndexError(SearchError):
    """인덱스 오류 (로드/빌드 실패)

    Example:
        raise IndexError("인덱스 로드 실패", details="faiss index corrupted")
    """
    def __init__(self, message: str = "인덱스 오류", details: str | None = None, code: ErrorCode | None = None):
        super().__init__(message, details, code or ErrorCode.E_INDEX_LOAD)


class RateLimitError(AppError):
    """요청 제한 초과

    Example:
        raise RateLimitError("요청 초과", details="limit=100/min")
    """
    def __init__(self, message: str = "요청 제한을 초과했습니다", details: str | None = None):
        super().__init__(message, details, code=None, status_code=429)


class RoutingError(AppError):
    """쿼리 라우팅 실패

    Example:
        raise RoutingError("모드 결정 실패", details="ambiguous query pattern")
    """
    def __init__(self, message: str = "쿼리 라우팅 오류", details: str | None = None):
        super().__init__(message, details, code=None, status_code=500)


class ContextHydrationError(AppError):
    """컨텍스트 수화 실패

    Example:
        raise ContextHydrationError("컨텍스트 구성 실패", details="no valid chunks")
    """
    def __init__(self, message: str = "컨텍스트 구성 오류", details: str | None = None):
        super().__init__(message, details, code=ErrorCode.E_COMPRESS, status_code=500)


class CacheError(AppError):
    """캐시 처리 실패 (일반)

    Example:
        raise CacheError("캐시 저장 실패", details="disk full")
    """
    def __init__(self, message: str = "캐시 오류", details: str | None = None):
        super().__init__(message, details, code=None, status_code=500)


# ============================================================================
# 로깅 유틸리티
# ============================================================================

def log_error(exc: AppError, level: int = logging.ERROR) -> None:
    """구조화된 에러 로그 기록

    Args:
        exc: AppError 또는 하위 클래스 인스턴스
        level: 로그 레벨 (기본: ERROR)

    Example:
        try:
            ...
        except Exception as e:
            err = SearchError("검색 실패", str(e), code=ErrorCode.E_RETRIEVE)
            log_error(err)
            raise err
    """
    log_data = exc.to_dict()
    # LogRecord의 message와 충돌 방지를 위해 extra에서 message 제거
    extra_data = {k: v for k, v in log_data.items() if k != "message"}
    logger.log(level, f"{exc.message}", extra=extra_data)


__all__ = [
    # 기본 예외
    "AppError",
    "ConfigError",
    "DatabaseError",
    "ModelError",
    "SearchError",
    "ValidationError",
    # 확장 예외 (Phase 3)
    "DocumentNotFoundError",
    "OCRProcessingError",
    "CacheExpiredError",
    "IndexError",
    "RateLimitError",
    # 확장 예외 (Phase 5 - RAG 파이프라인용)
    "RoutingError",
    "ContextHydrationError",
    "CacheError",
    # 유틸리티
    "ErrorCode",
    "ERROR_MESSAGES",
    "log_error",
]
