#!/usr/bin/env python3
"""
통합 로깅 유틸리티
기존 ChatLogger와 ErrorHandler를 쉽게 사용할 수 있는 래퍼
모든 모듈에서 일관된 로깅을 위한 유틸리티
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional
from functools import wraps
import logging

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

from modules.log_system import get_logger, ChatLogger, TimerContext
from utils.error_handler import ErrorHandler, handle_errors

# 싱글톤 로거 인스턴스
_unified_logger = None


class UnifiedLogger:
    """
    통합 로거 - ChatLogger와 ErrorHandler를 쉽게 사용할 수 있는 래퍼

    사용 예시:
        logger = get_unified_logger()
        logger.info("시스템 시작")
        logger.error("오류 발생", context="파일 읽기")

        # 타이머 사용
        with logger.timer("데이터베이스 검색"):
            # 작업 수행
            pass
    """

    def __init__(self, log_dir: str = None, module_name: str = None):
        """
        Args:
            log_dir: 로그 디렉토리 (기본: logs)
            module_name: 모듈명 (로그에 표시됨)
        """
        # ChatLogger 초기화
        self.chat_logger = get_logger() if log_dir is None else ChatLogger(log_dir)

        # 모듈명
        self.module_name = module_name or "system"

        # Python 표준 로거도 초기화 (추가 호환성)
        self.std_logger = logging.getLogger(self.module_name)

    def info(self, message: str, **kwargs):
        """정보 로그"""
        formatted_msg = f"[{self.module_name}] {message}"
        self.chat_logger.info(formatted_msg)
        self.std_logger.info(formatted_msg, **kwargs)

    def debug(self, message: str, **kwargs):
        """디버그 로그"""
        formatted_msg = f"[{self.module_name}] {message}"
        self.chat_logger.debug(formatted_msg)
        self.std_logger.debug(formatted_msg, **kwargs)

    def warning(self, message: str, **kwargs):
        """경고 로그"""
        formatted_msg = f"[{self.module_name}] {message}"
        self.chat_logger.warning(formatted_msg)
        self.std_logger.warning(formatted_msg, **kwargs)

    def error(self, message: str, exception: Exception = None, context: str = "", **kwargs):
        """에러 로그"""
        formatted_msg = f"[{self.module_name}] {message}"

        if exception:
            # ErrorHandler를 사용하여 처리
            ErrorHandler.handle(exception, context or self.module_name)

            # ChatLogger에도 기록
            self.chat_logger.log_error(
                error_type=type(exception).__name__,
                error_msg=str(exception),
                query=context
            )
        else:
            # 일반 에러 로그
            self.chat_logger.error(formatted_msg)
            self.std_logger.error(formatted_msg, **kwargs)

    def log_query(self, query: str, response: str, search_mode: str = None,
                  processing_time: float = None, metadata: Dict[str, Any] = None):
        """질문/답변 로깅 - ChatLogger 메서드 래핑"""
        return self.chat_logger.log_query(
            query=query,
            response=response,
            search_mode=search_mode,
            processing_time=processing_time,
            metadata=metadata
        )

    def log_performance(self, operation: str, duration: float, details: Dict[str, Any] = None):
        """성능 로깅 - ChatLogger 메서드 래핑"""
        self.chat_logger.log_performance(operation, duration, details)

    def timer(self, operation: str):
        """
        타이머 컨텍스트 매니저

        사용 예시:
            with logger.timer("데이터베이스 검색"):
                # 작업 수행
                pass
        """
        return TimerContext(self.chat_logger, operation)

    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return self.chat_logger.get_statistics()

    def safe_execute(self, func, *args, context: str = "", default_return=None, **kwargs):
        """
        안전한 함수 실행 래퍼

        사용 예시:
            result = logger.safe_execute(
                risky_function,
                arg1, arg2,
                context="데이터 처리",
                default_return=[]
            )
        """
        return ErrorHandler.safe_execute(func, *args, context=context,
                                        default_return=default_return, **kwargs)


def get_unified_logger(module_name: str = None, log_dir: str = None) -> UnifiedLogger:
    """
    통합 로거 인스턴스 반환

    Args:
        module_name: 모듈명 (예: "web_interface", "rag_system")
        log_dir: 로그 디렉토리 (기본: logs)

    Returns:
        UnifiedLogger 인스턴스
    """
    global _unified_logger

    # 모듈별로 다른 인스턴스를 원할 경우
    if module_name:
        return UnifiedLogger(log_dir=log_dir, module_name=module_name)

    # 싱글톤으로 사용할 경우
    if _unified_logger is None:
        _unified_logger = UnifiedLogger(log_dir=log_dir)

    return _unified_logger


def log_function_call(module_name: str = None):
    """
    함수 호출을 로깅하는 데코레이터

    사용 예시:
        @log_function_call("search_module")
        def search_documents(query):
            # 함수 내용
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_unified_logger(module_name or func.__module__)

            # 함수 호출 로그
            logger.debug(f"함수 호출: {func.__name__}")

            try:
                # 타이머로 성능 측정
                with logger.timer(f"{func.__module__}.{func.__name__}"):
                    result = func(*args, **kwargs)
                return result
            except Exception as e:
                # 에러 로깅
                logger.error(
                    f"함수 실행 오류: {func.__name__}",
                    exception=e,
                    context=f"{func.__module__}.{func.__name__}"
                )
                raise

        return wrapper
    return decorator


# 편의 함수들 (기존 코드와의 호환성을 위해)
def replace_print_with_logger(module_name: str):
    """
    print()를 logger로 교체하기 위한 헬퍼

    사용 예시:
        import sys
        sys.stdout.write = replace_print_with_logger("my_module")

    주의: 이 방법은 권장하지 않습니다. 직접 logger를 사용하세요.
    """
    logger = get_unified_logger(module_name)

    class LoggerWriter:
        def write(self, message):
            if message.strip():  # 빈 줄 제외
                logger.info(message.strip())

        def flush(self):
            pass

    return LoggerWriter()


# 테스트 코드
if __name__ == "__main__":
    # 기본 로거 테스트
    logger = get_unified_logger("test_module")

    logger.info("시스템 시작")
    logger.debug("디버그 메시지")
    logger.warning("경고 메시지")

    # 타이머 테스트
    import time
    with logger.timer("테스트 작업"):
        time.sleep(0.1)

    # 에러 처리 테스트
    try:
        raise ValueError("테스트 에러")
    except Exception as e:
        logger.error("에러 발생", exception=e, context="테스트")

    # 통계 출력
    import json
    stats = logger.get_statistics()
    print("\n=== 통계 ===")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    print("\n✅ 통합 로깅 유틸리티 테스트 완료!")
