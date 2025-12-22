"""app/core/logging.py 테스트"""

import logging
import time

import pytest

from app.core.logging import (
    JsonFormatter,
    UtcFormatter,
    get_logger,
    reset_logger,
    set_level,
)


class TestUtcFormatter:
    """UtcFormatter 테스트"""

    def test_converter_is_gmtime(self):
        """UTC 변환기 확인"""
        formatter = UtcFormatter()
        assert formatter.converter == time.gmtime


class TestJsonFormatter:
    """JsonFormatter 테스트"""

    def test_format_basic(self):
        """기본 JSON 포맷팅"""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="테스트 메시지",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert '"level": "INFO"' in output
        assert '"logger": "test"' in output
        assert '"msg": "테스트 메시지"' in output
        assert '"line": 10' in output

    def test_format_with_exception(self):
        """예외 정보 포함"""
        formatter = JsonFormatter()

        try:
            raise ValueError("테스트 에러")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=20,
            msg="에러 발생",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)

        assert '"exc_info"' in output
        assert "ValueError" in output

    def test_format_with_context_fields(self):
        """컨텍스트 필드 포함"""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=30,
            msg="요청 처리",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-123"
        record.user_id = "user-456"

        output = formatter.format(record)

        assert '"request_id": "req-123"' in output
        assert '"user_id": "user-456"' in output


class TestGetLogger:
    """get_logger() 테스트"""

    def teardown_method(self):
        """각 테스트 후 로거 리셋"""
        reset_logger()

    def test_get_root_logger(self):
        """루트 로거 가져오기"""
        logger = get_logger("app")
        assert logger.name == "app"

    def test_get_child_logger(self):
        """자식 로거 가져오기"""
        logger = get_logger("app.rag.pipeline")
        assert "app.rag.pipeline" in logger.name

    def test_singleton_pattern(self):
        """싱글톤 패턴 확인"""
        logger1 = get_logger("app")
        logger2 = get_logger("app")
        assert logger1 is logger2


class TestSetLevel:
    """set_level() 테스트"""

    def teardown_method(self):
        """각 테스트 후 로거 리셋"""
        reset_logger()

    def test_set_debug_level(self):
        """DEBUG 레벨 설정"""
        set_level("DEBUG")
        logger = get_logger("app")
        assert logger.level == logging.DEBUG

    def test_set_warning_level(self):
        """WARNING 레벨 설정"""
        set_level("WARNING")
        logger = get_logger("app")
        assert logger.level == logging.WARNING


class TestResetLogger:
    """reset_logger() 테스트"""

    def test_reset_clears_handlers(self):
        """핸들러 제거 확인"""
        logger = get_logger("app")
        initial_handlers = len(logger.handlers)
        assert initial_handlers > 0

        reset_logger()

        # 새로운 로거는 다시 초기화됨
        logger2 = get_logger("app")
        assert len(logger2.handlers) > 0
