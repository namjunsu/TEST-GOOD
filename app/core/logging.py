"""통합 로깅 시스템

모든 모듈은 이 모듈의 get_logger()를 사용합니다.

Example:
    >>> from app.core.logging import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("시스템 시작")
    >>> logger.error("오류 발생", exc_info=True)
"""

import logging
import sys
from pathlib import Path
from logging import Logger, StreamHandler, Formatter
from logging.handlers import RotatingFileHandler
from typing import Optional

# 전역 로거 (싱글톤)
_LOGGER: Optional[logging.Logger] = None
_INITIALIZED = False


def _init_logger() -> logging.Logger:
    """로거 초기화 (내부 함수)

    - 콘솔 핸들러 (INFO 이상)
    - 파일 핸들러 (DEBUG 이상, 로테이팅)
    """
    global _LOGGER, _INITIALIZED

    if _INITIALIZED and _LOGGER:
        return _LOGGER

    # 루트 로거 생성
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 포맷터
    console_fmt = Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    file_fmt = Formatter(
        "[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 콘솔 핸들러
    console_handler = StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 파일 핸들러 (로테이팅)
    log_dir = Path("var/log")
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    _LOGGER = logger
    _INITIALIZED = True

    logger.info("Logging system initialized")
    return logger


def get_logger(name: str = "app") -> Logger:
    """로거 팩토리 (전역 진입점)

    Args:
        name: 로거 이름 (보통 __name__ 사용)

    Returns:
        Logger: 설정된 로거

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("정보 메시지")
        >>> logger.warning("경고 메시지")
        >>> logger.error("오류 메시지", exc_info=True)
    """
    root_logger = _init_logger()
    return root_logger.getChild(name) if name != "app" else root_logger


def set_level(level: str) -> None:
    """로그 레벨 변경

    Args:
        level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    logger = _init_logger()
    logger.setLevel(getattr(logging, level.upper()))
    logger.info(f"Log level changed to {level.upper()}")
