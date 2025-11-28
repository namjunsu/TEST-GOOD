"""
성능 모니터링 유틸리티 테스트
시간 측정 정확도 및 메트릭 수집 검증
"""

import pytest
import time
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock streamlit with proper session_state
class MockSessionState:
    def __init__(self):
        self._data = {}

    def __setattr__(self, name, value):
        if name == '_data':
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __getattr__(self, name):
        return self._data.get(name)

    def __contains__(self, name):
        return name in self._data

    def __setitem__(self, name, value):
        self._data[name] = value

    def __getitem__(self, name):
        return self._data[name]

    def get(self, name, default=None):
        return self._data.get(name, default)

    def __delattr__(self, name):
        if name in self._data:
            del self._data[name]

    def clear(self):
        self._data.clear()

st_mock = MagicMock()
st_mock.session_state = MockSessionState()
st_mock.error = Mock()
st_mock.warning = Mock()
st_mock.info = Mock()
st_mock.caption = Mock()
st_mock.success = Mock()
st_mock.metric = Mock()
st_mock.markdown = Mock()
st_mock.expander = Mock(return_value=MagicMock(__enter__=Mock(), __exit__=Mock()))
st_mock.columns = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
st_mock.dataframe = Mock()

sys.modules['streamlit'] = st_mock
sys.modules['pandas'] = Mock()

# 이제 performance import
from utils.performance import PerformanceMonitor, Timer, benchmark


class TestPerformanceMonitor:
    """성능 모니터링 테스트"""

    def setup_method(self):
        """각 테스트 전 세션 상태 초기화"""
        st_mock.session_state.clear()

    def test_measure_decorator_basic(self):
        """기본 데코레이터 동작"""
        @PerformanceMonitor.measure
        def test_func():
            time.sleep(0.01)
            return "result"

        result = test_func()

        assert result == "result"
        assert 'performance_metrics' in st_mock.session_state

        metrics = st_mock.session_state['performance_metrics']
        func_key = f"{test_func.__module__}.test_func"
        assert func_key in metrics
        assert metrics[func_key]['count'] == 1
        assert metrics[func_key]['total_time'] >= 0.01
        assert metrics[func_key]['errors'] == 0

    def test_measure_decorator_with_name(self):
        """커스텀 이름 지정"""
        @PerformanceMonitor.measure(name="CustomFunction", show_time=False)
        def test_func():
            return "result"

        test_func()

        metrics = st_mock.session_state['performance_metrics']
        assert "CustomFunction" in metrics
        assert metrics["CustomFunction"]['count'] == 1

    def test_measure_decorator_error_tracking(self):
        """에러 발생 시 메트릭 추적"""
        @PerformanceMonitor.measure
        def failing_func():
            time.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_func()

        metrics = st_mock.session_state['performance_metrics']
        func_key = f"{failing_func.__module__}.failing_func"
        assert metrics[func_key]['count'] == 1
        assert metrics[func_key]['errors'] == 1
        assert metrics[func_key]['total_time'] >= 0.01

    def test_perf_counter_usage(self):
        """perf_counter 사용 확인"""
        with patch('time.perf_counter') as mock_perf:
            mock_perf.side_effect = [1.0, 1.5]  # 0.5초 경과

            @PerformanceMonitor.measure
            def test_func():
                return "result"

            test_func()

            # perf_counter가 두 번 호출되었는지 확인
            assert mock_perf.call_count == 2

            metrics = st_mock.session_state['performance_metrics']
            func_key = f"{test_func.__module__}.test_func"
            assert abs(metrics[func_key]['total_time'] - 0.5) < 0.001

    def test_multiple_calls_aggregation(self):
        """여러 번 호출 시 메트릭 집계"""
        @PerformanceMonitor.measure
        def test_func():
            time.sleep(0.01)

        # 3번 호출
        for _ in range(3):
            test_func()

        metrics = st_mock.session_state['performance_metrics']
        func_key = f"{test_func.__module__}.test_func"

        assert metrics[func_key]['count'] == 3
        assert metrics[func_key]['total_time'] >= 0.03
        assert metrics[func_key]['min_time'] >= 0.01
        assert metrics[func_key]['max_time'] >= metrics[func_key]['min_time']

    def test_debug_mode_display(self):
        """디버그 모드 표시 동작"""
        # 디버그 모드 활성화
        os.environ['DEBUG_MODE'] = 'true'

        @PerformanceMonitor.measure
        def slow_func():
            time.sleep(0.01)

        slow_func()

        # 디버그 모드에서 caption 호출 확인
        st_mock.caption.assert_called()

        # 디버그 모드 비활성화
        os.environ['DEBUG_MODE'] = 'false'
        st_mock.caption.reset_mock()

        slow_func()

        # 비활성화 시 caption 호출 안 됨
        st_mock.caption.assert_not_called()

        # 환경 변수 정리
        del os.environ['DEBUG_MODE']

    def test_get_summary(self):
        """요약 정보 생성"""
        @PerformanceMonitor.measure(name="func1")
        def func1():
            time.sleep(0.01)

        @PerformanceMonitor.measure(name="func2")
        def func2():
            time.sleep(0.02)

        func1()
        func1()
        func2()

        summary = PerformanceMonitor.get_summary()

        assert summary['total_functions'] == 2
        assert summary['total_calls'] == 3
        assert summary['total_time'] >= 0.04
        assert summary['avg_time'] >= 0.013
        assert summary['total_errors'] == 0
        assert summary['most_called']['name'] == 'func1'
        assert summary['most_called']['count'] == 2

    def test_reset_metrics(self):
        """메트릭 초기화"""
        @PerformanceMonitor.measure
        def test_func():
            pass

        test_func()
        assert 'performance_metrics' in st_mock.session_state

        # 메시지 표시 없이 초기화
        PerformanceMonitor.reset_metrics(show_message=False)
        assert 'performance_metrics' not in st_mock.session_state
        st_mock.success.assert_not_called()

        # 메시지 표시하며 초기화
        test_func()
        PerformanceMonitor.reset_metrics(show_message=True)
        st_mock.success.assert_called_once()


class TestTimer:
    """Timer 컨텍스트 매니저 테스트"""

    def setup_method(self):
        """각 테스트 전 세션 상태 초기화"""
        st_mock.session_state.clear()

    def test_timer_basic(self):
        """기본 타이머 동작"""
        with Timer("TestOperation", show=False) as timer:
            time.sleep(0.01)

        assert timer.duration >= 0.01
        assert timer.name == "TestOperation"

        # 메트릭에 저장되었는지 확인
        metrics = st_mock.session_state['performance_metrics']
        assert "TestOperation" in metrics
        assert metrics["TestOperation"]['count'] == 1

    def test_timer_debug_mode_integration(self):
        """Timer의 디버그 모드 통합"""
        os.environ['DEBUG_MODE'] = 'true'

        with Timer("SlowOp") as timer:
            time.sleep(0.01)

        # 디버그 모드에서 표시
        st_mock.caption.assert_called()

        # 디버그 모드 비활성화
        os.environ['DEBUG_MODE'] = 'false'
        st_mock.caption.reset_mock()

        with Timer("FastOp"):
            pass

        # 비활성화 시 표시 안 함
        st_mock.caption.assert_not_called()

        del os.environ['DEBUG_MODE']

    def test_timer_exception_handling(self):
        """Timer 내 예외 발생 처리"""
        with pytest.raises(ValueError):
            with Timer("ErrorOp", show=False):
                raise ValueError("Test error")

        # 예외가 발생해도 메트릭은 저장됨
        metrics = st_mock.session_state['performance_metrics']
        assert "ErrorOp" in metrics
        assert metrics["ErrorOp"]['count'] == 1

    def test_timer_perf_counter(self):
        """Timer의 perf_counter 사용"""
        with patch('time.perf_counter') as mock_perf:
            mock_perf.side_effect = [1.0, 1.5]

            with Timer("TestOp", show=False) as timer:
                pass

            assert abs(timer.duration - 0.5) < 0.001
            assert mock_perf.call_count == 2


class TestBenchmark:
    """벤치마크 데코레이터 테스트"""

    def test_benchmark_decorator(self):
        """벤치마크 데코레이터 동작"""
        call_count = 0

        @benchmark(iterations=10)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = test_func(5)

        assert result == 10
        assert call_count == 10

    def test_benchmark_timing_accuracy(self):
        """벤치마크 시간 측정 정확도"""
        with patch('time.perf_counter') as mock_perf:
            # 10번 반복, 각 0.1초
            mock_perf.side_effect = [i * 0.1 for i in range(21)]

            @benchmark(iterations=10)
            def test_func():
                return "result"

            with patch.object(PerformanceMonitor.logger, 'info') as mock_log:
                result = test_func()

                # 로그 메시지 확인
                mock_log.assert_called_once()
                log_message = mock_log.call_args[0][0]
                assert "avg=100.000ms" in log_message
                assert "10 iterations" in log_message


class TestPerformanceThresholds:
    """성능 임계값 테스트"""

    def setup_method(self):
        """각 테스트 전 세션 상태 초기화"""
        st_mock.session_state.clear()

    def test_slow_threshold(self):
        """SLOW_THRESHOLD 경고"""
        @PerformanceMonitor.measure
        def slow_func():
            time.sleep(1.1)  # SLOW_THRESHOLD = 1.0 초과

        with patch.object(PerformanceMonitor.logger, 'info') as mock_log:
            slow_func()
            mock_log.assert_called()
            assert "Slow:" in mock_log.call_args[0][0]

    def test_critical_threshold(self):
        """CRITICAL_THRESHOLD 경고"""
        @PerformanceMonitor.measure
        def very_slow_func():
            time.sleep(0.01)  # 테스트 시간 단축

        # 임계값 임시 조정
        original = PerformanceMonitor.CRITICAL_THRESHOLD
        PerformanceMonitor.CRITICAL_THRESHOLD = 0.005

        with patch.object(PerformanceMonitor.logger, 'warning') as mock_log:
            very_slow_func()
            mock_log.assert_called()
            assert "Critical:" in mock_log.call_args[0][0]

        # 원래 값 복원
        PerformanceMonitor.CRITICAL_THRESHOLD = original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])