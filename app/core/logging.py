"""통합 로깅 시스템

모든 모듈은 이 모듈의 get_logger()를 사용합니다.

운영 환경 개선사항:
- UTC 타임스탬프 (감사 추적)
- JSON 로그 지원 (SIEM/ELK 연동)
- 중복 핸들러 방지 (재기동 안전)
- 환경변수 제어 (LOG_LEVEL, LOG_JSON, LOG_MAX_MB, LOG_BACKUP)
- Uvicorn/FastAPI 로거 통합

환경변수:
    LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (기본: INFO)
    LOG_JSON: true/false (기본: false)
    LOG_MAX_MB: 로그 파일 최대 크기 MB (기본: 10)
    LOG_BACKUP: 백업 파일 개수 (기본: 5)
    LOG_DIR: 로그 디렉토리 (기본: var/log, settings에서 가져옴)

Example:
    >>> from app.core.logging import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("시스템 시작")
    >>> logger.error("오류 발생", exc_info=True)
"""

from __future__ import annotations
import logging
import json
import sys
import os
import time
from pathlib import Path
from logging import Logger, StreamHandler, Formatter, LogRecord
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any

# settings 모듈에서 LOG_DIR 가져오기 (fallback: 환경변수)
try:
    from app.config.settings import settings
    LOG_DIR = settings.LOG_DIR
except Exception:
    LOG_DIR = Path(os.getenv("LOG_DIR", "var/log")).resolve()

# 전역 로거 (싱글톤)
_LOGGER: Optional[logging.Logger] = None


# ============================================================================
# UTC 포맷터
# ============================================================================

class UtcFormatter(Formatter):
    """UTC 타임스탬프 포맷터 (운영 감사 추적용)"""
    converter = time.gmtime  # UTC로 변환


class JsonFormatter(Formatter):
    """JSON 로그 포맷터 (SIEM/ELK/Loki 연동용)

    출력 형식:
        {"ts": "2025-01-11T12:34:56Z", "level": "ERROR", "logger": "app.rag",
         "msg": "검색 실패", "module": "hybrid", "line": 123, "exc_info": "..."}
    """

    def format(self, record: LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # 예외 정보 포함
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # 요청 ID 등 컨텍스트 필드 자동 포함 (있으면)
        for key in ("request_id", "user_id", "trace_id", "session_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)


# ============================================================================
# 로거 초기화
# ============================================================================

def _init_logger() -> logging.Logger:
    """로거 초기화 (내부 함수)

    환경변수:
        LOG_LEVEL: 로그 레벨 (기본: INFO)
        LOG_JSON: JSON 포맷 사용 (기본: false)
        LOG_MAX_MB: 파일 최대 크기 MB (기본: 10)
        LOG_BACKUP: 백업 파일 개수 (기본: 5)

    Returns:
        Logger: 설정된 루트 로거
    """
    global _LOGGER

    if _LOGGER:
        return _LOGGER

    # 환경변수 읽기
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    json_mode = os.getenv("LOG_JSON", "false").lower() == "true"
    max_mb = int(os.getenv("LOG_MAX_MB", "10"))
    backups = int(os.getenv("LOG_BACKUP", "5"))

    # 로그 레벨 검증
    level = getattr(logging, level_name, logging.INFO)

    # 루트 로거 생성
    logger = logging.getLogger("app")
    logger.setLevel(level)
    logger.propagate = False

    # 중복 핸들러 제거 (재기동/리로드 대비)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # 포맷터 선택
    if json_mode:
        console_fmt = JsonFormatter()
        file_fmt = JsonFormatter()
    else:
        console_fmt = UtcFormatter(
            "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
        file_fmt = UtcFormatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # 콘솔 핸들러
    console_handler = StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 파일 핸들러 (로테이팅)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(LOG_DIR / "app.log"),  # Path → str 명시
            maxBytes=max_mb * 1024 * 1024,
            backupCount=backups,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # 파일은 상세 수집
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"파일 핸들러 초기화 실패: {e}")

    # 외부 프레임워크 로거 레벨 정렬 (Uvicorn/FastAPI)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        ext_logger = logging.getLogger(name)
        ext_logger.setLevel(level)
        # Uvicorn 기본 핸들러 제거하고 우리 핸들러로 통합 (선택)
        # ext_logger.handlers.clear()
        # ext_logger.propagate = True  # app 로거로 전파

    logger.info(
        "Logging system initialized (level=%s, json=%s, dir=%s)",
        level_name,
        json_mode,
        str(LOG_DIR)
    )

    _LOGGER = logger
    return logger


# ============================================================================
# 공개 API
# ============================================================================

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
    return root_logger if name == "app" else root_logger.getChild(name)


def set_level(level: str) -> None:
    """로그 레벨 동적 변경 (런타임)

    Args:
        level: DEBUG, INFO, WARNING, ERROR, CRITICAL

    Example:
        >>> from app.core.logging import set_level
        >>> set_level("DEBUG")  # 디버깅 모드 활성화
    """
    logger = _init_logger()
    target_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(target_level)

    # 모든 핸들러 레벨 업데이트
    for handler in logger.handlers:
        if isinstance(handler, StreamHandler):
            handler.setLevel(target_level)
        # 파일 핸들러는 항상 DEBUG 유지 (선택)

    logger.info("Log level changed to %s", level.upper())


def reset_logger() -> None:
    """로거 초기화 (테스트용)

    주의: 프로덕션 환경에서는 사용 금지
    """
    global _LOGGER
    if _LOGGER:
        for handler in list(_LOGGER.handlers):
            _LOGGER.removeHandler(handler)
        _LOGGER = None


__all__ = ["get_logger", "set_level", "reset_logger"]
