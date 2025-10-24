"""
성능 모니터링 유틸리티
함수 실행 시간 측정 및 메트릭 수집
"""

import time
import streamlit as st
from functools import wraps
from typing import Dict, Any, Optional
import logging


class PerformanceMonitor:
    """성능 모니터링 클래스"""

    # 로거 설정
    logger = logging.getLogger(__name__)

    # 성능 임계값 (초)
    SLOW_THRESHOLD = 1.0
    CRITICAL_THRESHOLD = 5.0

    @classmethod
    def measure(cls, func=None, *, name: str = None, show_time: bool = True):
        """
        함수 실행 시간 측정 데코레이터

        Usage:
            @PerformanceMonitor.measure
            def slow_function():
                time.sleep(2)

            @PerformanceMonitor.measure(name="Custom Name", show_time=False)
            def another_function():
                pass
        """
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                func_name = name or f.__name__

                # 시작 시간
                start_time = time.time()

                try:
                    # 함수 실행
                    result = f(*args, **kwargs)

                    # 실행 시간 계산
                    duration = time.time() - start_time

                    # 메트릭 저장
                    cls._store_metric(func_name, duration)

                    # 시간 표시 (옵션)
                    if show_time:
                        cls._display_timing(func_name, duration)

                    # 로깅
                    if duration > cls.CRITICAL_THRESHOLD:
                        cls.logger.warning(f"Critical: {func_name} took {duration:.2f}s")
                    elif duration > cls.SLOW_THRESHOLD:
                        cls.logger.info(f"Slow: {func_name} took {duration:.2f}s")

                    return result

                except Exception as e:
                    # 에러 발생 시에도 시간 측정
                    duration = time.time() - start_time
                    cls._store_metric(func_name, duration, error=True)
                    cls.logger.error(f"{func_name} failed after {duration:.2f}s: {e}")
                    raise

            return wrapper

        # 데코레이터가 인자 없이 사용된 경우
        if func is not None:
            return decorator(func)

        # 데코레이터가 인자와 함께 사용된 경우
        return decorator

    @classmethod
    def _store_metric(cls, func_name: str, duration: float, error: bool = False):
        """메트릭 저장"""
        if 'performance_metrics' not in st.session_state:
            st.session_state.performance_metrics = {}

        if func_name not in st.session_state.performance_metrics:
            st.session_state.performance_metrics[func_name] = {
                'count': 0,
                'total_time': 0.0,
                'min_time': float('inf'),
                'max_time': 0.0,
                'errors': 0
            }

        metrics = st.session_state.performance_metrics[func_name]
        metrics['count'] += 1
        metrics['total_time'] += duration
        metrics['min_time'] = min(metrics['min_time'], duration)
        metrics['max_time'] = max(metrics['max_time'], duration)
        if error:
            metrics['errors'] += 1

    @classmethod
    def _display_timing(cls, func_name: str, duration: float):
        """실행 시간 표시"""
        if cls._is_debug_mode():
            if duration > cls.CRITICAL_THRESHOLD:
                st.error(f"⏱️ {func_name}: {duration:.2f}s (매우 느림!)")
            elif duration > cls.SLOW_THRESHOLD:
                st.warning(f"⏱️ {func_name}: {duration:.2f}s (느림)")
            else:
                st.caption(f"⏱️ {func_name}: {duration:.3f}s")

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """수집된 메트릭 반환"""
        return st.session_state.get('performance_metrics', {})

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """메트릭 요약 정보"""
        metrics = cls.get_metrics()
        if not metrics:
            return {}

        summary = {
            'total_functions': len(metrics),
            'total_calls': sum(m['count'] for m in metrics.values()),
            'total_time': sum(m['total_time'] for m in metrics.values()),
            'total_errors': sum(m['errors'] for m in metrics.values()),
            'slowest_function': None,
            'fastest_function': None,
            'most_called': None
        }

        # 가장 느린 함수
        slowest = max(metrics.items(), key=lambda x: x[1]['max_time'])
        summary['slowest_function'] = {
            'name': slowest[0],
            'time': slowest[1]['max_time']
        }

        # 가장 빠른 함수
        fastest = min(metrics.items(), key=lambda x: x[1]['min_time'])
        summary['fastest_function'] = {
            'name': fastest[0],
            'time': fastest[1]['min_time']
        }

        # 가장 많이 호출된 함수
        most_called = max(metrics.items(), key=lambda x: x[1]['count'])
        summary['most_called'] = {
            'name': most_called[0],
            'count': most_called[1]['count']
        }

        return summary

    @classmethod
    def display_report(cls):
        """성능 보고서 표시"""
        summary = cls.get_summary()
        if not summary:
            st.info("아직 수집된 성능 데이터가 없습니다")
            return

        st.markdown("### 📊 성능 보고서")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("총 함수", summary['total_functions'])

        with col2:
            st.metric("총 호출", summary['total_calls'])

        with col3:
            st.metric("총 시간", f"{summary['total_time']:.2f}s")

        with col4:
            st.metric("에러", summary['total_errors'])

        # 상세 정보
        with st.expander("📈 상세 메트릭"):
            metrics = cls.get_metrics()
            for func_name, data in metrics.items():
                avg_time = data['total_time'] / data['count'] if data['count'] > 0 else 0
                st.text(f"""
                함수: {func_name}
                  - 호출 횟수: {data['count']}
                  - 평균 시간: {avg_time:.3f}s
                  - 최소 시간: {data['min_time']:.3f}s
                  - 최대 시간: {data['max_time']:.3f}s
                  - 에러 횟수: {data['errors']}
                """)

    @classmethod
    def reset_metrics(cls):
        """메트릭 초기화"""
        if 'performance_metrics' in st.session_state:
            del st.session_state.performance_metrics
        st.success("성능 메트릭이 초기화되었습니다")

    @classmethod
    def _is_debug_mode(cls) -> bool:
        """디버그 모드 확인"""
        import os
        return os.getenv('DEBUG_MODE', '').lower() in ['true', '1', 'yes']


# 컨텍스트 매니저로 사용할 수 있는 타이머
class Timer:
    """
    컨텍스트 매니저 타이머

    Usage:
        with Timer("데이터 로드"):
            # 시간을 측정할 코드
            load_data()
    """

    def __init__(self, name: str = "Operation", show: bool = True):
        self.name = name
        self.show = show
        self.start_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        if self.show:
            if self.duration > PerformanceMonitor.SLOW_THRESHOLD:
                st.warning(f"⏱️ {self.name}: {self.duration:.2f}s")
            else:
                st.caption(f"⏱️ {self.name}: {self.duration:.3f}s")