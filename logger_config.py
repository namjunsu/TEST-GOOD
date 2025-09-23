"""
중앙 집중식 로깅 시스템 설정
================================

프로덕션 환경을 위한 구조화된 로깅
"""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import os

# 환경 설정
ENV = os.getenv('ENVIRONMENT', 'development')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = os.getenv('LOG_FORMAT', 'json')
LOG_FILE = os.getenv('LOG_FILE', 'logs/app.log')


class JsonFormatter(logging.Formatter):
    """JSON 형식 로그 포매터"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process': record.process,
            'thread': record.thread,
            'environment': ENV
        }

        # 예외 정보 추가
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        # 추가 컨텍스트
        if hasattr(record, 'context'):
            log_obj['context'] = record.context

        # 성능 메트릭
        if hasattr(record, 'metrics'):
            log_obj['metrics'] = record.metrics

        return json.dumps(log_obj, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """컬러 콘솔 출력용 포매터"""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        return super().format(record)


class ContextFilter(logging.Filter):
    """컨텍스트 정보 추가 필터"""

    def __init__(self, app_name: str = 'ai-chat'):
        super().__init__()
        self.app_name = app_name
        self.hostname = os.uname().nodename

    def filter(self, record: logging.LogRecord) -> bool:
        record.app = self.app_name
        record.hostname = self.hostname
        record.environment = ENV
        return True


class PerformanceLogger:
    """성능 메트릭 로거"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_api_request(self,
                       method: str,
                       path: str,
                       status: int,
                       duration_ms: float,
                       **kwargs):
        """API 요청 로깅"""
        self.logger.info(
            f"API Request: {method} {path}",
            extra={
                'metrics': {
                    'type': 'api_request',
                    'method': method,
                    'path': path,
                    'status': status,
                    'duration_ms': duration_ms,
                    **kwargs
                }
            }
        )

    def log_search_performance(self,
                              query: str,
                              mode: str,
                              results: int,
                              duration_ms: float,
                              cached: bool = False):
        """검색 성능 로깅"""
        self.logger.info(
            f"Search completed: {results} results",
            extra={
                'metrics': {
                    'type': 'search',
                    'query_length': len(query),
                    'mode': mode,
                    'results': results,
                    'duration_ms': duration_ms,
                    'cached': cached
                }
            }
        )

    def log_model_loading(self,
                         model_name: str,
                         load_time_s: float,
                         memory_gb: float):
        """모델 로딩 로깅"""
        self.logger.info(
            f"Model loaded: {model_name}",
            extra={
                'metrics': {
                    'type': 'model_loading',
                    'model': model_name,
                    'load_time_s': load_time_s,
                    'memory_gb': memory_gb
                }
            }
        )


def setup_logger(name: str = __name__,
                level: Optional[str] = None,
                log_file: Optional[str] = None) -> logging.Logger:
    """로거 설정 및 반환"""

    logger = logging.getLogger(name)

    # 이미 설정된 경우 반환
    if logger.handlers:
        return logger

    # 로그 레벨 설정
    level = level or LOG_LEVEL
    logger.setLevel(getattr(logging, level.upper()))

    # 컨텍스트 필터 추가
    logger.addFilter(ContextFilter())

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    if LOG_FORMAT == 'json':
        console_handler.setFormatter(JsonFormatter())
    else:
        # 개발 환경용 컬러 포맷
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러
    log_file = log_file or LOG_FILE
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # 로테이팅 파일 핸들러 (10MB, 10개 백업)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    # 에러 파일 핸들러 (ERROR 이상만)
    error_log = log_file.replace('.log', '_error.log') if log_file else 'logs/error.log'
    if error_log:
        Path(error_log).parent.mkdir(parents=True, exist_ok=True)
        error_handler = logging.handlers.RotatingFileHandler(
            error_log,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JsonFormatter())
        logger.addHandler(error_handler)

    return logger


def get_logger(name: str = __name__) -> logging.Logger:
    """기본 로거 가져오기"""
    return setup_logger(name)


def log_exception(logger: logging.Logger,
                 exc: Exception,
                 context: Optional[Dict[str, Any]] = None):
    """예외 로깅 헬퍼"""
    logger.error(
        f"Exception occurred: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={'context': context or {}}
    )


# 전역 로거 인스턴스
root_logger = setup_logger('ai-chat')
api_logger = setup_logger('ai-chat.api')
search_logger = setup_logger('ai-chat.search')
model_logger = setup_logger('ai-chat.model')

# 성능 로거
perf_logger = PerformanceLogger(setup_logger('ai-chat.performance'))


if __name__ == "__main__":
    # 로깅 테스트
    logger = get_logger()

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    # 성능 로깅 테스트
    perf_logger.log_api_request(
        method="GET",
        path="/search",
        status=200,
        duration_ms=142.5
    )

    # 예외 로깅 테스트
    try:
        1 / 0
    except Exception as e:
        log_exception(logger, e, {'operation': 'test_division'})

    print("\n✅ 로깅 시스템 설정 완료!")