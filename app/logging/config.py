"""
Centralized Logging Configuration
표준 로그 스키마 및 회전 정책 적용
"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Optional
import json
from datetime import datetime
import uuid


class StructuredFormatter(logging.Formatter):
    """구조화된 JSON 로그 포맷터"""

    def format(self, record: logging.LogRecord) -> str:
        # Base structured log
        log_data = {
            "ts": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add trace_id if present
        if hasattr(record, 'trace_id'):
            log_data["trace_id"] = record.trace_id

        # Add req_id if present
        if hasattr(record, 'req_id'):
            log_data["req_id"] = record.req_id

        # Add RAG-specific fields if present
        if hasattr(record, 'mode'):
            log_data["mode"] = record.mode

        if hasattr(record, 'has_code'):
            log_data["has_code"] = record.has_code

        if hasattr(record, 'stage0_count'):
            log_data["stage0_count"] = record.stage0_count

        if hasattr(record, 'stage1_count'):
            log_data["stage1_count"] = record.stage1_count

        if hasattr(record, 'rrf_weight'):
            log_data["rrf_weight"] = record.rrf_weight

        if hasattr(record, 'latency_ms'):
            log_data["latency_ms"] = record.latency_ms

        if hasattr(record, 'doc_locked'):
            log_data["doc_locked"] = record.doc_locked

        if hasattr(record, 'coverage'):
            log_data["coverage"] = record.coverage

        # Exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    rotation_days: int = 1,
    retention_days: int = 7,
    structured: bool = False
) -> logging.Logger:
    """
    중앙화된 로깅 설정

    Args:
        log_dir: 로그 디렉토리
        log_level: 로그 레벨
        rotation_days: 로그 회전 주기 (일)
        retention_days: 로그 보존 기간 (일)
        structured: 구조화된 JSON 로그 사용 여부

    Returns:
        configured logger
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get root logger
    logger = logging.getLogger()

    # Clear existing handlers
    logger.handlers.clear()

    # Set level
    logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    if structured:
        console_formatter = StructuredFormatter()
    else:
        console_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)-8s %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = TimedRotatingFileHandler(
        filename=log_path / "ai-chat.log",
        when='midnight',
        interval=rotation_days,
        backupCount=retention_days,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    if structured:
        file_formatter = StructuredFormatter()
    else:
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)-8s %(name)s: %(message)s'
        )

    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Error log (separate file)
    error_handler = TimedRotatingFileHandler(
        filename=log_path / "ai-chat-error.log",
        when='midnight',
        interval=rotation_days,
        backupCount=retention_days,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def add_context(logger: logging.Logger, **kwargs):
    """Add contextual information to logger"""
    adapter = logging.LoggerAdapter(logger, kwargs)
    return adapter


# Request ID context manager
class RequestContext:
    """Request context for distributed tracing"""

    def __init__(self):
        self.req_id = None
        self.trace_id = None

    def __enter__(self):
        self.req_id = str(uuid.uuid4())[:8]
        self.trace_id = str(uuid.uuid4())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.req_id = None
        self.trace_id = None

    def add_to_record(self, record: logging.LogRecord):
        """Add context to log record"""
        if self.req_id:
            record.req_id = self.req_id
        if self.trace_id:
            record.trace_id = self.trace_id


# Singleton context
_request_context = RequestContext()


def get_request_context() -> RequestContext:
    """Get global request context"""
    return _request_context
