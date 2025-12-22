"""app.core.errors 모듈 단위 테스트

테스트 대상:
- AppError 및 하위 클래스 생성
- to_dict() 직렬화
- to_http() FastAPI 변환
- log_error() 로깅
- ErrorCode Enum 사용
"""

import logging

import pytest

from app.core.errors import (
    ERROR_MESSAGES,
    AppError,
    ConfigError,
    DatabaseError,
    ErrorCode,
    ModelError,
    SearchError,
    ValidationError,
    log_error,
)


class TestAppError:
    """AppError 기본 기능 테스트"""

    def test_basic_creation(self):
        """기본 예외 생성"""
        err = AppError("테스트 메시지")
        assert err.message == "테스트 메시지"
        assert err.details is None
        assert err.code is None
        assert err.status_code == 500

    def test_with_details(self):
        """상세 정보 포함"""
        err = AppError("메시지", details="상세 내용")
        assert err.message == "메시지"
        assert err.details == "상세 내용"
        assert "상세 내용" in str(err)

    def test_with_error_code(self):
        """에러 코드 포함"""
        err = AppError("메시지", code=ErrorCode.E_TIMEOUT)
        assert err.code == ErrorCode.E_TIMEOUT
        assert err.code.value == "E_TIMEOUT"

    def test_to_dict(self):
        """딕셔너리 직렬화"""
        err = SearchError("검색 실패", details="인덱스 없음", code=ErrorCode.E_INDEX_LOAD)
        result = err.to_dict()

        assert result["type"] == "SearchError"
        assert result["message"] == "검색 실패"
        assert result["details"] == "인덱스 없음"
        assert result["code"] == "E_INDEX_LOAD"
        assert result["status_code"] == 500


class TestSubclasses:
    """하위 예외 클래스 테스트"""

    def test_config_error(self):
        """ConfigError 기본 생성"""
        err = ConfigError("설정 오류")
        assert err.status_code == 500
        assert isinstance(err, AppError)

    def test_database_error(self):
        """DatabaseError 상태 코드"""
        err = DatabaseError("DB 오류", code=ErrorCode.E_DB_BUSY)
        assert err.status_code == 503
        assert err.code == ErrorCode.E_DB_BUSY

    def test_model_error(self):
        """ModelError 상태 코드"""
        err = ModelError("모델 로드 실패", code=ErrorCode.E_MODEL_LOAD)
        assert err.status_code == 503

    def test_search_error(self):
        """SearchError 기본 생성"""
        err = SearchError("검색 실패", details="인덱스 파일 없음")
        assert err.status_code == 500
        assert err.details == "인덱스 파일 없음"

    def test_validation_error(self):
        """ValidationError 상태 코드 (400)"""
        err = ValidationError("입력 검증 실패", details="빈 문자열")
        assert err.status_code == 400


class TestFastAPIIntegration:
    """FastAPI 연동 테스트"""

    def test_to_http_basic(self):
        """to_http() 기본 변환"""
        from typing import Any, cast

        err = SearchError("검색 실패", code=ErrorCode.E_RETRIEVE)
        http_exc = err.to_http()
        detail = cast(dict[str, Any], http_exc.detail)

        assert http_exc.status_code == 500
        assert detail["error"] == "E_RETRIEVE"
        assert detail["message"] == "검색 실패"

    def test_to_http_with_details(self):
        """to_http() 상세 정보 포함"""
        from typing import Any, cast

        err = DatabaseError("DB 오류", details="timeout 5s", code=ErrorCode.E_DB_LOCK)
        http_exc = err.to_http()
        detail = cast(dict[str, Any], http_exc.detail)

        assert http_exc.status_code == 503
        assert detail["details"] == "timeout 5s"
        assert detail["error"] == "E_DB_LOCK"

    def test_to_http_validation_error(self):
        """ValidationError HTTP 400 변환"""
        err = ValidationError("빈 질문")
        http_exc = err.to_http()

        assert http_exc.status_code == 400


class TestLogging:
    """로깅 유틸리티 테스트"""

    def test_log_error_basic(self):
        """log_error() 기본 로깅 - mock 사용"""
        from unittest.mock import patch

        with patch("app.core.errors.logger") as mock_logger:
            err = SearchError("검색 실패", details="인덱스 로드 오류", code=ErrorCode.E_INDEX_LOAD)
            log_error(err)

            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.ERROR
            assert "검색 실패" in call_args[0][1]

    def test_log_error_level(self):
        """log_error() 로그 레벨 지정 - mock 사용"""
        from unittest.mock import patch

        with patch("app.core.errors.logger") as mock_logger:
            err = ValidationError("입력 검증 실패")
            log_error(err, level=logging.WARNING)

            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.WARNING


class TestErrorCode:
    """ErrorCode Enum 테스트"""

    def test_enum_values(self):
        """Enum 값 확인"""
        assert ErrorCode.E_RETRIEVE.value == "E_RETRIEVE"
        assert ErrorCode.E_INDEX_LOAD.value == "E_INDEX_LOAD"
        assert ErrorCode.E_TIMEOUT.value == "E_TIMEOUT"

    def test_enum_membership(self):
        """Enum 멤버십 확인"""
        assert ErrorCode.E_RETRIEVE in ErrorCode
        assert "E_RETRIEVE" == ErrorCode.E_RETRIEVE.value

    def test_error_messages_mapping(self):
        """ERROR_MESSAGES 매핑 확인"""
        assert ErrorCode.E_RETRIEVE in ERROR_MESSAGES
        assert "검색" in ERROR_MESSAGES[ErrorCode.E_RETRIEVE]

        assert ErrorCode.E_MODEL_LOAD in ERROR_MESSAGES
        assert "모델" in ERROR_MESSAGES[ErrorCode.E_MODEL_LOAD]


class TestUsageExamples:
    """실제 사용 예시 테스트"""

    def test_raise_and_catch(self):
        """예외 발생 및 포착"""
        with pytest.raises(SearchError) as exc_info:
            raise SearchError("검색 실패", details="타임아웃", code=ErrorCode.E_TIMEOUT)

        err = exc_info.value
        assert err.message == "검색 실패"
        assert err.code == ErrorCode.E_TIMEOUT

    def test_logging_workflow(self):
        """로깅 워크플로우 - mock 사용"""
        from unittest.mock import patch

        with patch("app.core.errors.logger") as mock_logger:
            try:
                # 가상 검색 실패
                raise Exception("인덱스 파일 없음")
            except Exception as e:
                err = SearchError("검색 중 오류", str(e), code=ErrorCode.E_INDEX_LOAD)
                log_error(err)
                # 실제로는 여기서 raise err 하겠지만 테스트에서는 생략

            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert "검색 중 오류" in call_args[0][1]

    def test_fastapi_workflow(self):
        """FastAPI 워크플로우"""
        from typing import Any, cast

        try:
            raise DatabaseError("DB 연결 실패", details="타임아웃", code=ErrorCode.E_DB_BUSY)
        except DatabaseError as e:
            http_exc = e.to_http()
            detail = cast(dict[str, Any], http_exc.detail)
            assert http_exc.status_code == 503
            assert detail["error"] == "E_DB_BUSY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
