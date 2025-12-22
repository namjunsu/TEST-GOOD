"""
system_checker.py 버그 수정 검증 테스트
사용자가 지적한 4가지 핵심 버그가 수정되었는지 확인

테스트 목록:
1. 캐시 로드 시 self.result 갱신 확인
2. logger.exception() 사용 확인 (logger.error(exception=e) 제거)
3. 캐시 버전 관리 확인
4. config.py 검사가 WARN으로 변경되었는지 확인
"""

import os
import pickle
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# streamlit mock은 conftest.py에서 전역으로 설정됨

# system_checker import
from utils.system_checker import CheckResult, CheckStatus, SystemChecker


class TestCacheResultSync:
    """버그 1: 캐시 로드 시 self.result 갱신 확인"""

    def test_cached_result_updates_self_result(self, tmp_path):
        """캐시를 로드했을 때 self.result가 갱신되는지 확인"""
        # 임시 캐시 파일 생성
        cache_file = tmp_path / ".system_check_cache.pkl"

        # 가짜 캐시 데이터 생성 (버전 포함)
        from utils.system_checker import CheckItem
        fake_result = CheckResult()
        fake_result.add_item(CheckItem(
            name="test_item",
            status=CheckStatus.PASS,
            message="Cached test item"
        ))

        payload = {
            "version": 2,
            "result": fake_result
        }

        with open(cache_file, "wb") as f:
            pickle.dump(payload, f)

        # SystemChecker 생성 (캐시 파일 경로 오버라이드)
        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            checker = SystemChecker(verbose=False, use_cache=True)

            # check_all() 호출 전 self.result는 비어있음
            assert len(checker.result.items) == 0

            # check_all() 호출 (캐시 로드 발생)
            result = checker.check_all()

            # 반환된 result와 self.result가 동일한 객체인지 확인
            assert result is checker.result

            # self.result에 캐시된 항목이 있는지 확인
            assert len(checker.result.items) > 0
            assert checker.result.items[0].name == "test_item"
            assert checker.result.items[0].message == "Cached test item"

            # to_json() 호출 시 캐시된 결과를 반영하는지 확인
            json_output = checker.to_json()
            assert "Cached test item" in json_output

    def test_to_json_reflects_cached_result(self, tmp_path):
        """to_json()이 캐시된 결과를 올바르게 직렬화하는지 확인"""
        cache_file = tmp_path / ".system_check_cache.pkl"

        from utils.system_checker import CheckItem
        fake_result = CheckResult()
        fake_result.add_item(CheckItem(
            name="cached_check",
            status=CheckStatus.PASS,
            message="This is from cache"
        ))
        fake_result.metrics["test_metric"] = 123

        payload = {
            "version": 2,
            "result": fake_result
        }

        with open(cache_file, "wb") as f:
            pickle.dump(payload, f)

        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            checker = SystemChecker(verbose=False, use_cache=True)
            checker.check_all()

            # to_json() 결과 확인
            result_dict = checker.result.to_dict()

            assert result_dict["passed"][0]["message"] == "This is from cache"
            assert result_dict["metrics"]["test_metric"] == 123


class TestLoggerExceptionUsage:
    """버그 2: logger.error(exception=e) → logger.exception() 변경 확인"""

    def test_logger_exception_called_on_parallel_check_error(self):
        """병렬 검사 실패 시 logger.exception() 호출 확인"""
        checker = SystemChecker(verbose=False, parallel=True, use_cache=False)

        # 실패하는 검사 함수
        def failing_check():
            raise ValueError("Test error")

        with patch("utils.system_checker.logger") as mock_logger:
            with patch("utils.system_checker.LOGGING_AVAILABLE", True):
                # 병렬 검사 실행
                checker._run_parallel_checks([("Test", failing_check)], 1)

                # logger.exception이 호출되었는지 확인
                mock_logger.exception.assert_called_once()
                assert "검사 실패" in mock_logger.exception.call_args[0][0]

                # logger.error는 호출되지 않았는지 확인
                # (exception 키워드 인자 사용하는 호출이 없어야 함)
                for call in mock_logger.error.call_args_list:
                    if call[1]:  # kwargs가 있으면
                        assert "exception" not in call[1]

    def test_logger_exception_called_on_sequential_check_error(self):
        """순차 검사 실패 시 logger.exception() 호출 확인"""
        checker = SystemChecker(verbose=False, parallel=False, use_cache=False)

        def failing_check():
            raise RuntimeError("Sequential test error")

        with patch("utils.system_checker.logger") as mock_logger:
            with patch("utils.system_checker.LOGGING_AVAILABLE", True):
                checker._run_sequential_checks([("Test", failing_check)], 1)

                mock_logger.exception.assert_called_once()
                assert "검사 실패" in mock_logger.exception.call_args[0][0]


class TestCacheVersionManagement:
    """버그 3: 캐시 버전 관리 확인"""

    def test_old_cache_version_ignored(self, tmp_path):
        """구 버전 캐시는 무시되고 재검사가 실행되는지 확인"""
        cache_file = tmp_path / ".system_check_cache.pkl"

        # 구 버전 캐시 (버전 1)
        from utils.system_checker import CheckItem
        old_result = CheckResult()
        old_result.add_item(CheckItem(
            name="old_item",
            status=CheckStatus.PASS,
            message="Old cache data"
        ))

        old_payload = {
            "version": 1,  # 구 버전 (현재는 v2)
            "result": old_result
        }

        with open(cache_file, "wb") as f:
            pickle.dump(old_payload, f)

        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            checker = SystemChecker(verbose=False, use_cache=True, show_progress=False)

            # check_all() 호출
            result = checker.check_all()

            # 구 버전 캐시는 무시되고 새 검사가 실행되어야 함
            # (old_item이 아닌 실제 검사 결과가 있어야 함)
            item_names = [item.name for item in result.items]
            assert "old_item" not in item_names

            # 실제 검사가 수행되었는지 확인 (python_version 등 기본 검사 존재)
            assert "python_version" in item_names

    def test_cache_version_in_saved_payload(self, tmp_path):
        """저장된 캐시에 버전 메타데이터가 포함되는지 확인"""
        cache_file = tmp_path / ".system_check_cache.pkl"

        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            checker = SystemChecker(verbose=False, use_cache=True, show_progress=False)

            # 검사 실행 (캐시 저장됨)
            checker.check_all()

            # 캐시 파일 내용 확인
            with open(cache_file, "rb") as f:
                payload = pickle.load(f)

            # 버전 필드 존재 확인
            assert "version" in payload
            assert payload["version"] == 2

            # result 필드 존재 확인
            assert "result" in payload
            assert isinstance(payload["result"], CheckResult)

    def test_invalid_cache_structure_handled(self, tmp_path):
        """잘못된 캐시 구조가 안전하게 처리되는지 확인"""
        cache_file = tmp_path / ".system_check_cache.pkl"

        # 구 형식 캐시 (딕셔너리가 아닌 CheckResult 직접 저장)
        from utils.system_checker import CheckItem
        old_format_result = CheckResult()
        old_format_result.add_item(CheckItem(
            name="invalid",
            status=CheckStatus.PASS,
            message="Invalid format"
        ))

        with open(cache_file, "wb") as f:
            pickle.dump(old_format_result, f)  # payload 딕셔너리 없이 직접 저장

        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            checker = SystemChecker(verbose=False, use_cache=True, show_progress=False)

            # 오류 없이 새 검사 실행되어야 함
            result = checker.check_all()

            # 실제 검사가 수행되었는지 확인
            item_names = [item.name for item in result.items]
            assert "invalid" not in item_names
            assert "python_version" in item_names


class TestConfigCheckPolicy:
    """버그 4: config.py 검사 정책이 WARN으로 변경되었는지 확인"""

    def test_missing_config_py_is_warn_not_fail(self, tmp_path):
        """config.py 파일이 없을 때 WARN 상태로 처리되는지 확인"""
        # 임시 프로젝트 루트 설정
        fake_root = tmp_path / "fake_project"
        fake_root.mkdir()

        with patch("utils.system_checker.project_root", fake_root):
            checker = SystemChecker(verbose=False, use_cache=False, show_progress=False)
            checker.check_config_files()

            # config_file 항목 찾기
            config_items = [item for item in checker.result.items if item.name == "config_file"]

            if config_items:
                config_item = config_items[0]

                # FAIL이 아닌 WARN이어야 함
                assert config_item.status == CheckStatus.WARN

                # 메시지에 "app.config.settings 사용 가능" 언급 확인
                assert "app.config.settings" in config_item.message

                # action이 "필요시" 같은 선택적 표현 포함 확인
                assert config_item.action is not None and "필요시" in config_item.action

    def test_config_check_continues_without_config_py(self, tmp_path):
        """config.py가 없어도 검사가 계속 진행되는지 확인"""
        fake_root = tmp_path / "fake_project"
        fake_root.mkdir()

        # app 디렉터리 구조 생성 (config.py 없이)
        (fake_root / "app").mkdir()
        (fake_root / "app" / "config").mkdir()

        with patch("utils.system_checker.project_root", fake_root):
            checker = SystemChecker(verbose=False, use_cache=False, show_progress=False)
            checker.check_config_files()

            # 에러가 없어야 함 (WARN만 있음)
            assert len(checker.result.errors) == 0


class TestIntegrationAllFixes:
    """통합 테스트: 모든 수정사항이 함께 동작하는지 확인"""

    def test_full_workflow_with_cache(self, tmp_path):
        """캐시 저장 → 로드 → JSON 출력 전체 흐름 테스트"""
        cache_file = tmp_path / ".system_check_cache.pkl"

        with patch.object(SystemChecker, "CACHE_FILE", cache_file):
            # 첫 번째 실행 (캐시 저장)
            checker1 = SystemChecker(verbose=False, use_cache=True, show_progress=False)
            _result1 = checker1.check_all()

            # 캐시 파일 생성 확인
            assert cache_file.exists()

            # 두 번째 실행 (캐시 로드)
            checker2 = SystemChecker(verbose=False, use_cache=True, show_progress=False)
            _result2 = checker2.check_all()

            # self.result가 올바르게 갱신되었는지 확인
            assert len(checker2.result.items) > 0

            # JSON 출력 테스트
            json_output = checker2.to_json()
            assert len(json_output) > 0

            # JSON에 실제 검사 결과가 포함되어 있는지 확인
            import json
            json_data = json.loads(json_output)
            total_items = (
                len(json_data.get("passed", [])) +
                len(json_data.get("warnings", [])) +
                len(json_data.get("errors", []))
            )
            assert total_items > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
