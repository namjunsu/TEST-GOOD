"""
통합 에러 처리 모듈
일관된 에러 처리 및 사용자 친화적 메시지 제공

Version: 2.0
- Streamlit 의존성 선택적 처리 (백엔드/CLI 호환)
- functools.wraps로 메타데이터 보존
- 로깅 전략 개선 (ErrorType 포함)
- safe_execute에 show_details 인자 추가
"""

import functools
import logging
import traceback
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

# Streamlit 선택적 임포트
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


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
    """통합 에러 처리기 (Streamlit/Console 겸용)"""

    # 로거 설정
    logger = logging.getLogger(__name__)

    @classmethod
    def handle(
        cls,
        error: Exception,
        context: str = "",
        show_details: bool = True,
        use_console: bool = False
    ) -> None:
        """
        에러 타입별 처리

        Args:
            error: 발생한 예외
            context: 에러 발생 컨텍스트
            show_details: 상세 정보 표시 여부
            use_console: 콘솔 출력 강제 (Streamlit 무시)
        """
        error_type = cls._classify_error(error)
        message = cls._get_user_message(error_type, error, context)
        icon = cls._get_error_icon(error_type)

        # 로깅 (ErrorType 포함)
        cls.logger.error(
            "ErrorType=%s, context=%s, error=%s",
            error_type.name,
            context or "unknown",
            str(error),
            exc_info=True
        )

        # UI/콘솔 출력 분기
        if _HAS_STREAMLIT and not use_console:
            cls._handle_streamlit(error, error_type, message, icon, show_details, context)
        else:
            cls._handle_console(error, error_type, message, icon, show_details, context)

    @classmethod
    def _handle_streamlit(
        cls,
        error: Exception,
        error_type: ErrorType,
        message: str,
        icon: str,
        show_details: bool,
        context: str
    ) -> None:
        """Streamlit UI 처리"""
        # 사용자에게 표시
        if error_type in [ErrorType.FILE_NOT_FOUND, ErrorType.PERMISSION_DENIED]:
            st.warning(f"{icon} {message}")
        else:
            st.error(f"{icon} {message}")

        # 해결 방법 제안
        solution = cls._get_solution(error_type)
        if solution:
            st.info(f"💡 {solution}")

        # 디버그 모드이거나 show_details가 True일 때 상세 정보
        if show_details and cls._is_debug_mode():
            with st.expander("🔍 상세 오류 정보"):
                st.text(f"오류 타입: {type(error).__name__}")
                st.text(f"오류 메시지: {str(error)}")
                st.text(f"컨텍스트: {context or 'N/A'}")
                st.text("\n스택 트레이스:")
                st.text(traceback.format_exc())

    @classmethod
    def _handle_console(
        cls,
        error: Exception,
        error_type: ErrorType,
        message: str,
        icon: str,
        show_details: bool,
        context: str
    ) -> None:
        """콘솔 출력 처리 (백엔드/CLI용)"""
        # 콘솔 색상 코드 (선택적)
        RED = "\033[91m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        RESET = "\033[0m"

        # 에러 수준에 따른 출력
        if error_type in [ErrorType.FILE_NOT_FOUND, ErrorType.PERMISSION_DENIED]:
            print(f"{YELLOW}{icon} {message}{RESET}")
        else:
            print(f"{RED}{icon} {message}{RESET}")

        # 해결 방법 제안
        solution = cls._get_solution(error_type)
        if solution:
            print(f"{BLUE}💡 {solution}{RESET}")

        # 상세 정보 (디버그 모드)
        if show_details:
            print("\n--- 상세 오류 정보 ---")
            print(f"오류 타입: {type(error).__name__}")
            print(f"오류 메시지: {str(error)}")
            print(f"컨텍스트: {context or 'N/A'}")
            if cls._is_debug_mode(console_fallback=True):
                print("\n스택 트레이스:")
                print(traceback.format_exc())

    @classmethod
    def _classify_error(cls, error: Exception) -> ErrorType:
        """에러 타입 분류"""
        error_str = str(error).lower()

        # 구체적인 Exception 타입 우선 체크
        if isinstance(error, FileNotFoundError):
            return ErrorType.FILE_NOT_FOUND
        elif isinstance(error, PermissionError):
            return ErrorType.PERMISSION_DENIED
        elif isinstance(error, MemoryError):
            return ErrorType.MEMORY_ERROR
        elif isinstance(error, TimeoutError):
            return ErrorType.TIMEOUT_ERROR
        elif isinstance(error, ImportError):
            return ErrorType.IMPORT_ERROR

        # 메시지 기반 분류
        elif "database" in error_str or "sqlite" in error_str:
            return ErrorType.DATABASE_ERROR
        elif any(kw in error_str for kw in ["network", "connection", "requests.exceptions", "urllib"]):
            return ErrorType.NETWORK_ERROR
        elif "ocr" in error_str or "tesseract" in error_str:
            return ErrorType.OCR_ERROR
        elif "pdf" in error_str or "pypdf" in error_str:
            return ErrorType.PDF_ERROR
        elif "index" in error_str or "faiss" in error_str or "bm25" in error_str:
            return ErrorType.INDEX_ERROR

        return ErrorType.UNKNOWN

    @classmethod
    def _get_user_message(cls, error_type: ErrorType, error: Exception, context: str) -> str:
        """사용자 친화적 메시지 생성"""
        base_message = error_type.value

        if context:
            base_message = f"{base_message} (작업: {context})"

        # 특정 에러 타입에 대한 추가 정보
        if error_type == ErrorType.FILE_NOT_FOUND:
            filename = cls._extract_filename(str(error))
            if filename:
                base_message = f"파일을 찾을 수 없습니다: {filename}"

        return base_message

    @classmethod
    def _extract_filename(cls, error_str: str) -> Optional[str]:
        """에러 메시지에서 파일명 추출 (다양한 확장자 지원)"""
        import re
        patterns = [
            r"'([^']+\.(pdf|docx|pptx|txt|csv))'",
            r'"([^"]+\.(pdf|docx|pptx|txt|csv))"',
            r"([^\s]+\.(pdf|docx|pptx|txt|csv))",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_str, re.IGNORECASE)
            if match:
                return Path(match.group(1)).name

        return None

    @classmethod
    def _get_error_icon(cls, error_type: ErrorType) -> str:
        """에러 타입별 아이콘"""
        icons = {
            ErrorType.FILE_NOT_FOUND: "📂",
            ErrorType.PERMISSION_DENIED: "🔒",
            ErrorType.MEMORY_ERROR: "💾",
            ErrorType.DATABASE_ERROR: "🗄️",
            ErrorType.NETWORK_ERROR: "🌐",
            ErrorType.OCR_ERROR: "📷",
            ErrorType.PDF_ERROR: "📑",
            ErrorType.IMPORT_ERROR: "📦",
            ErrorType.INDEX_ERROR: "🔍",
            ErrorType.TIMEOUT_ERROR: "⏱️",
            ErrorType.UNKNOWN: "❌"
        }
        return icons.get(error_type, "❗")

    @classmethod
    def _get_solution(cls, error_type: ErrorType) -> Optional[str]:
        """에러 타입별 해결 방법 제안"""
        solutions = {
            ErrorType.FILE_NOT_FOUND: "파일 경로를 확인하거나 파일이 존재하는지 확인하세요.",
            ErrorType.PERMISSION_DENIED: "파일 권한을 확인하세요. (chmod/chown 필요할 수 있음)",
            ErrorType.MEMORY_ERROR: "메모리 사용량을 확인하고 불필요한 프로세스를 종료하세요.",
            ErrorType.DATABASE_ERROR: "데이터베이스를 재인덱싱 해보세요. (사이드바 > ♻️ 전체재인덱싱)",
            ErrorType.NETWORK_ERROR: "네트워크 연결을 확인하거나 잠시 후 다시 시도하세요.",
            ErrorType.OCR_ERROR: "Tesseract OCR이 설치되어 있는지 확인하세요. (sudo apt-get install tesseract-ocr-kor)",
            ErrorType.PDF_ERROR: "PDF 파일이 손상되지 않았는지 확인하세요.",
            ErrorType.IMPORT_ERROR: "필요한 패키지를 설치하세요. (pip install -r requirements.txt)",
            ErrorType.INDEX_ERROR: "인덱스를 재구축하세요. (python scripts/rebuild_rag_indexes.py)",
            ErrorType.TIMEOUT_ERROR: "작업 시간이 초과되었습니다. 데이터 양을 줄이거나 타임아웃 설정을 늘려보세요."
        }
        return solutions.get(error_type)

    @classmethod
    def _is_debug_mode(cls, console_fallback: bool = False) -> bool:
        """디버그 모드 확인"""
        # Streamlit 세션 확인
        if _HAS_STREAMLIT and not console_fallback:
            try:
                if "debug_mode" in st.session_state:
                    return st.session_state.debug_mode
            except (AttributeError, RuntimeError):
                pass

        # 환경 변수 확인 (백엔드/CLI 호환)
        import os
        return os.getenv("DEBUG", "").lower() in ["true", "1", "yes"]

    @classmethod
    def safe_execute(
        cls,
        func: Callable,
        *args,
        context: str = "",
        default_return: Any = None,
        show_details: bool = True,
        **kwargs
    ) -> Any:
        """
        안전한 함수 실행 (에러 시 기본값 반환)

        Args:
            func: 실행할 함수
            *args: 위치 인자
            context: 에러 컨텍스트
            default_return: 에러 시 반환할 기본값
            show_details: 상세 정보 표시 여부
            **kwargs: 키워드 인자

        Returns:
            함수 실행 결과 또는 기본값
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            cls.handle(e, context or func.__name__, show_details=show_details)
            return default_return


def handle_errors(
    context: str = "",
    show_details: bool = True,
    default_return: Any = None
) -> Callable:
    """
    에러 처리 데코레이터

    Args:
        context: 에러 컨텍스트
        show_details: 상세 정보 표시 여부
        default_return: 에러 시 반환할 기본값

    Returns:
        데코레이터 함수

    Example:
        @handle_errors(context="PDF 로드", show_details=False)
        def load_pdf(path):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)  # 원 함수 메타데이터 보존
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ErrorHandler.handle(
                    e,
                    context or func.__name__,
                    show_details=show_details
                )
                return default_return
        return wrapper
    return decorator
