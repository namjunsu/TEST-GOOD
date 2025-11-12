"""
Centralized Logging Configuration
표준 로그 스키마 및 회전 정책 적용
contextvars 기반 동시성 안전 컨텍스트 전파
"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Optional
import json
from datetime import datetime, timezone
import uuid
import contextvars


# --- 안전한 컨텍스트 전파 (contextvars + Filter) ---
_req_id_var = contextvars.ContextVar("req_id", default=None)
_trace_id_var = contextvars.ContextVar("trace_id", default=None)


def set_request_ids(req_id: Optional[str], trace_id: Optional[str]):
    """
    현재 컨텍스트에 req_id/trace_id 설정

    Args:
        req_id: 요청 ID (8자 hex)
        trace_id: 추적 ID (UUID hex)
    """
    if req_id is not None:
        _req_id_var.set(req_id)
    if trace_id is not None:
        _trace_id_var.set(trace_id)


class ContextFilter(logging.Filter):
    """req_id/trace_id를 모든 LogRecord에 주입"""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _req_id_var.get()
        tid = _trace_id_var.get()
        if rid:
            record.req_id = rid
        if tid:
            record.trace_id = tid
        return True


class StructuredFormatter(logging.Formatter):
    """구조화된 JSON 로그 포맷터 (UTC + 확장 필드)"""

    def format(self, record: logging.LogRecord) -> str:
        # Base structured log with UTC timestamp
        log_data = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.thread,
            "pathname": record.pathname,
            "lineno": record.lineno,
        }

        # Add context IDs if present
        if hasattr(record, 'trace_id'):
            log_data["trace_id"] = record.trace_id
        if hasattr(record, 'req_id'):
            log_data["req_id"] = record.req_id

        # Add RAG-specific fields if present
        for field in ("mode", "has_code", "stage0_count", "stage1_count",
                     "rrf_weight", "latency_ms", "doc_locked", "coverage"):
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        # Exception info (일관된 키: exc_text)
        if record.exc_info:
            log_data["exc_text"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    rotation_days: int = 1,
    retention_files: int = 7,  # backupCount = 파일 개수 (일 1회 회전 기준)
    structured: bool = False
) -> logging.Logger:
    """
    중앙화된 로깅 설정 (app 네임스페이스 격리)

    Args:
        log_dir: 로그 디렉토리
        log_level: 로그 레벨 (DEBUG/INFO/WARNING/ERROR)
        rotation_days: 로그 회전 주기 (일)
        retention_files: 보존 파일 개수 (backupCount, 일 1회 회전 시 = 보존 일수)
        structured: 구조화된 JSON 로그 사용 여부

    Returns:
        'app' 네임스페이스 로거

    Note:
        - 루트 로거를 건드리지 않고 'app' 로거만 구성
        - Uvicorn/Gunicorn 핸들러와 충돌 방지
        - 모든 핸들러에 ContextFilter 적용으로 req_id/trace_id 자동 주입
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get 'app' namespace logger (루트 로거 건드리지 않음)
    logger = logging.getLogger("app")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    # 중복 방지: 기존 핸들러 제거
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # 포맷터 준비
    if structured:
        console_formatter = StructuredFormatter()
        file_formatter = StructuredFormatter()
    else:
        console_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)-8s %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ContextFilter())
    logger.addHandler(console_handler)

    # File handler with rotation (UTC 기준 회전)
    file_handler = TimedRotatingFileHandler(
        filename=str(log_path / "ai-chat.log"),
        when='midnight',
        interval=rotation_days,
        backupCount=retention_files,
        encoding='utf-8',
        utc=True  # UTC 기준 회전
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(ContextFilter())
    logger.addHandler(file_handler)

    # Error log (separate file)
    error_handler = TimedRotatingFileHandler(
        filename=str(log_path / "ai-chat-error.log"),
        when='midnight',
        interval=rotation_days,
        backupCount=retention_files,
        encoding='utf-8',
        utc=True
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    error_handler.addFilter(ContextFilter())
    logger.addHandler(error_handler)

    # 외부 로거 레벨 동기화 (Uvicorn 등)
    external_loggers = ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]
    for name in external_loggers:
        ext_logger = logging.getLogger(name)
        ext_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    logger.info(
        "Logging system initialized (level=%s, json=%s, dir=%s)",
        log_level.upper(),
        structured,
        log_dir,
        extra={"coverage": "global", "latency_ms": 0}
    )

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    로거 인스턴스 가져오기

    Args:
        name: 로거 이름 (권장: 'app.module_name')

    Returns:
        logging.Logger
    """
    return logging.getLogger(name)


def add_context(logger: logging.Logger, **kwargs):
    """
    로거에 컨텍스트 정보 추가

    Args:
        logger: 로거 인스턴스
        **kwargs: 추가할 컨텍스트 정보

    Returns:
        logging.LoggerAdapter
    """
    return logging.LoggerAdapter(logger, kwargs)


# Request ID context manager (contextvars 기반)
class RequestContext:
    """
    요청 컨텍스트 관리자 (비동기/멀티스레드 안전)

    Usage:
        with RequestContext():
            logger.info("request started")  # req_id/trace_id 자동 주입
    """

    def __init__(self):
        self._req_id = None
        self._trace_id = None

    def __enter__(self):
        self._req_id = uuid.uuid4().hex[:8]
        self._trace_id = uuid.uuid4().hex
        set_request_ids(self._req_id, self._trace_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 컨텍스트 종료 시 클리어 (선택적)
        set_request_ids(None, None)
        return False

    @property
    def req_id(self) -> Optional[str]:
        """현재 요청 ID"""
        return self._req_id

    @property
    def trace_id(self) -> Optional[str]:
        """현재 추적 ID"""
        return self._trace_id


# Singleton context (하위 호환용, 실제로는 contextvars 사용)
_request_context = RequestContext()


def get_request_context() -> RequestContext:
    """
    글로벌 요청 컨텍스트 가져오기

    Returns:
        RequestContext 인스턴스

    Note:
        실제 req_id/trace_id는 contextvars에 저장되므로
        여러 요청이 동시에 처리되어도 안전
    """
    return _request_context
