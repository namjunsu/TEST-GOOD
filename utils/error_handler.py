"""
통합 에러 처리 모듈
일관된 에러 처리 및 사용자 친화적 메시지 제공
"""

import streamlit as st
import logging
from enum import Enum
from typing import Optional
import traceback
from pathlib import Path


class ErrorType(Enum):
    """에러 타입 분류"""
    FILE_NOT_FOUND = "파일을 찾을 수 없습니다"
    PERMISSION_DENIED = "파일 접근 권한이 없습니다"
    MEMORY_ERROR = "메모리가 부족합니다"
    DATABASE_ERROR = "데이터베이스 오류"
    NETWORK_ERROR = "네트워크 오류"
    OCR_ERROR = "OCR 처리 오류"
    PDF_ERROR = "PDF 처리 오류"
    IMPORT_ERROR = "모듈 임포트 오류"
    INDEX_ERROR = "인덱싱 오류"
    TIMEOUT_ERROR = "시간 초과"
    UNKNOWN = "예상치 못한 오류"


class ErrorHandler:
    """통합 에러 처리기"""

    # 로거 설정
    logger = logging.getLogger(__name__)

    @classmethod
    def handle(cls, error: Exception, context: str = "", show_details: bool = True) -> None:
        """
        에러 타입별 처리

        Args:
            error: 발생한 예외
            context: 에러 발생 컨텍스트
            show_details: 상세 정보 표시 여부
        """
        error_type = cls._classify_error(error)
        message = cls._get_user_message(error_type, error, context)

        # 에러 타입에 따른 아이콘 선택
        icon = cls._get_error_icon(error_type)

        # 사용자에게 표시
        if error_type in [ErrorType.FILE_NOT_FOUND, ErrorType.PERMISSION_DENIED]:
            st.warning(f"{icon} {message}")
        else:
            st.error(f"{icon} {message}")

        # 해결 방법 제안
        solution = cls._get_solution(error_type)
        if solution:
            st.info(f"💡 {solution}")

        # 로깅
        cls.logger.error(f"{context}: {error}", exc_info=True)

        # 디버그 모드이거나 show_details가 True일 때 상세 정보
        if show_details and cls._is_debug_mode():
            with st.expander("🔍 상세 오류 정보"):
                st.text(f"오류 타입: {type(error).__name__}")
                st.text(f"오류 메시지: {str(error)}")
                st.text("\n스택 트레이스:")
                st.text(traceback.format_exc())

    @classmethod
    def _classify_error(cls, error: Exception) -> ErrorType:
        """에러 타입 분류"""
        error_str = str(error).lower()

        if isinstance(error, FileNotFoundError):
            return ErrorType.FILE_NOT_FOUND
        elif isinstance(error, PermissionError):
            return ErrorType.PERMISSION_DENIED
        elif isinstance(error, MemoryError):
            return ErrorType.MEMORY_ERROR
        elif isinstance(error, ImportError):
            return ErrorType.IMPORT_ERROR
        elif isinstance(error, IndexError):
            return ErrorType.INDEX_ERROR
        elif isinstance(error, TimeoutError):
            return ErrorType.TIMEOUT_ERROR
        elif "database" in error_str or "sqlite" in error_str:
            return ErrorType.DATABASE_ERROR
        elif "network" in error_str or "connection" in error_str:
            return ErrorType.NETWORK_ERROR
        elif "ocr" in error_str or "tesseract" in error_str:
            return ErrorType.OCR_ERROR
        elif "pdf" in error_str or "pypdf" in error_str:
            return ErrorType.PDF_ERROR
        else:
            return ErrorType.UNKNOWN

    @classmethod
    def _get_error_icon(cls, error_type: ErrorType) -> str:
        """에러 타입별 아이콘 반환"""
        icons = {
            ErrorType.FILE_NOT_FOUND: "📁",
            ErrorType.PERMISSION_DENIED: "🔒",
            ErrorType.MEMORY_ERROR: "💾",
            ErrorType.DATABASE_ERROR: "🗄️",
            ErrorType.NETWORK_ERROR: "🌐",
            ErrorType.OCR_ERROR: "🔍",
            ErrorType.PDF_ERROR: "📄",
            ErrorType.IMPORT_ERROR: "📦",
            ErrorType.INDEX_ERROR: "📋",
            ErrorType.TIMEOUT_ERROR: "⏱️",
            ErrorType.UNKNOWN: "❌"
        }
        return icons.get(error_type, "❌")

    @classmethod
    def _get_user_message(cls, error_type: ErrorType, error: Exception, context: str) -> str:
        """사용자 친화적 메시지 생성"""
        base_message = error_type.value

        if context:
            base_message = f"{context}: {base_message}"

        # 타입별 추가 정보
        if error_type == ErrorType.FILE_NOT_FOUND:
            filename = cls._extract_filename(str(error))
            if filename:
                return f"{base_message} - '{filename}'"
        elif error_type == ErrorType.MEMORY_ERROR:
            return f"{base_message} - 대용량 파일 처리 중"
        elif error_type == ErrorType.DATABASE_ERROR:
            return f"{base_message} - 인덱스가 손상되었을 수 있습니다"

        return base_message

    @classmethod
    def _get_solution(cls, error_type: ErrorType) -> Optional[str]:
        """에러 타입별 해결 방법 제안"""
        solutions = {
            ErrorType.FILE_NOT_FOUND: "파일이 이동되었거나 삭제되었을 수 있습니다. 재인덱싱을 시도해보세요.",
            ErrorType.PERMISSION_DENIED: "파일이 다른 프로그램에서 사용 중이거나 권한이 제한되어 있습니다.",
            ErrorType.MEMORY_ERROR: "파일 크기를 줄이거나 시스템을 재시작하세요.",
            ErrorType.DATABASE_ERROR: "데이터베이스를 재인덱싱 해보세요. (사이드바 > ♻️ 전체재인덱싱)",
            ErrorType.NETWORK_ERROR: "네트워크 연결을 확인하고 다시 시도하세요.",
            ErrorType.OCR_ERROR: "Tesseract OCR이 설치되어 있는지 확인하세요. (sudo apt-get install tesseract-ocr-kor)",
            ErrorType.PDF_ERROR: "PDF 파일이 손상되었을 수 있습니다. 다른 뷰어로 열어보세요.",
            ErrorType.IMPORT_ERROR: "필요한 패키지를 설치하세요. (pip install -r requirements.txt)",
            ErrorType.INDEX_ERROR: "인덱스를 재구축하세요. (python rebuild_rag_indexes.py)",
            ErrorType.TIMEOUT_ERROR: "작업 시간이 너무 깁니다. 작은 파일로 시도하거나 나중에 다시 시도하세요."
        }
        return solutions.get(error_type)

    @classmethod
    def _extract_filename(cls, error_message: str) -> Optional[str]:
        """에러 메시지에서 파일명 추출"""
        # 다양한 패턴으로 파일명 추출 시도
        import re
        patterns = [
            r"'([^']+\.pdf)'",
            r'"([^"]+\.pdf)"',
            r'([^\s]+\.pdf)',
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return Path(match.group(1)).name

        return None

    @classmethod
    def _is_debug_mode(cls) -> bool:
        """디버그 모드 확인"""
        # 세션 상태에서 디버그 모드 확인
        if 'debug_mode' in st.session_state:
            return st.session_state.debug_mode

        # 환경 변수에서 확인
        import os
        return os.getenv('DEBUG_MODE', '').lower() in ['true', '1', 'yes']

    @classmethod
    def safe_execute(cls, func, *args, context: str = "", default_return=None, **kwargs):
        """
        안전한 함수 실행 래퍼

        Args:
            func: 실행할 함수
            args: 함수 인자
            context: 에러 컨텍스트
            default_return: 에러 시 반환할 기본값
            kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과 또는 기본값
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            cls.handle(e, context)
            return default_return


# 데코레이터로 사용할 수 있는 헬퍼 함수
def handle_errors(context: str = "", show_details: bool = True):
    """
    에러 처리 데코레이터

    Usage:
        @handle_errors(context="PDF 미리보기")
        def show_pdf_preview(file_path):
            # 위험한 작업
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ErrorHandler.handle(e, context or func.__name__, show_details)
                return None
        return wrapper
    return decorator