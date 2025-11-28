"""
성능 모니터링 유틸리티
함수 실행 시간 측정 및 메트릭 수집

방송 기술관리팀 시스템 성능 최적화:
- 정확한 시간 측정 (perf_counter 사용)
- 세션별 메트릭 집계
- DataFrame 기반 시각화
- 디버그 모드 통합 관리
"""

import logging
import os
import time
from functools import wraps
from typing import Any

import pandas as pd
import streamlit as st


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

        Args:
            func: 측정할 함수
            name: 커스텀 함수 이름
            show_time: UI에 시간 표시 여부

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
                # 함수 이름 결정 (모듈 경로 포함 가능)
                func_name = name or f"{f.__module__}.{f.__name__}"

                # 시작 시간 (perf_counter 사용으로 정확도 향상)
                start_time = time.perf_counter()

                try:
                    # 함수 실행
                    result = f(*args, **kwargs)

                    # 실행 시간 계산
                    duration = time.perf_counter() - start_time

                    # 메트릭 저장
                    cls._store_metric(func_name, duration)

                    # 시간 표시 (디버그 모드 확인)
                    if show_time:
                        cls._display_timing(func_name, duration)

                    # 로깅
                    if duration > cls.CRITICAL_THRESHOLD:
                        cls.logger.warning(f"Critical: {func_name} took {duration:.2f}s")
                    elif duration > cls.SLOW_THRESHOLD:
                        cls.logger.info(f"Slow: {func_name} took {duration:.2f}s")
                    else:
                        cls.logger.debug(f"{func_name} took {duration:.3f}s")

                    return result

                except Exception as e:
                    # 에러 발생 시에도 시간 측정
                    duration = time.perf_counter() - start_time
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
        if "performance_metrics" not in st.session_state:
            st.session_state.performance_metrics = {}

        # setdefault로 코드 단순화
        metrics = st.session_state.performance_metrics.setdefault(
            func_name,
            {
                "count": 0,
                "total_time": 0.0,
                "min_time": float("inf"),
                "max_time": 0.0,
                "errors": 0,
            },
        )

        metrics["count"] += 1
        metrics["total_time"] += duration
        metrics["min_time"] = min(metrics["min_time"], duration)
        metrics["max_time"] = max(metrics["max_time"], duration)
        if error:
            metrics["errors"] += 1

    @classmethod
    def _display_timing(cls, func_name: str, duration: float):
        """실행 시간 표시 (디버그 모드일 때만)"""
        if cls._is_debug_mode():
            if duration > cls.CRITICAL_THRESHOLD:
                st.error(f"⏱️ {func_name}: {duration:.2f}s (매우 느림!)")
            elif duration > cls.SLOW_THRESHOLD:
                st.warning(f"⏱️ {func_name}: {duration:.2f}s (느림)")
            else:
                st.caption(f"⏱️ {func_name}: {duration:.3f}s")

    @classmethod
    def get_metrics(cls) -> dict[str, Any]:
        """수집된 메트릭 반환"""
        return st.session_state.get("performance_metrics", {})

    @classmethod
    def get_summary(cls) -> dict[str, Any]:
        """메트릭 요약 정보 (평균 시간 추가)"""
        metrics = cls.get_metrics()
        if not metrics:
            return {}

        total_calls = sum(m["count"] for m in metrics.values())
        total_time = sum(m["total_time"] for m in metrics.values())

        summary = {
            "total_functions": len(metrics),
            "total_calls": total_calls,
            "total_time": total_time,
            "avg_time": total_time / total_calls if total_calls > 0 else 0.0,
            "total_errors": sum(m["errors"] for m in metrics.values()),
            "slowest_function": None,
            "fastest_function": None,
            "most_called": None,
        }

        # 가장 느린 함수
        if metrics:
            slowest = max(metrics.items(), key=lambda x: x[1]["max_time"])
            summary["slowest_function"] = {
                "name": slowest[0],
                "time": slowest[1]["max_time"],
            }

            # 가장 빠른 함수
            fastest = min(metrics.items(), key=lambda x: x[1]["min_time"])
            summary["fastest_function"] = {
                "name": fastest[0],
                "time": fastest[1]["min_time"],
            }

            # 가장 많이 호출된 함수
            most_called = max(metrics.items(), key=lambda x: x[1]["count"])
            summary["most_called"] = {
                "name": most_called[0],
                "count": most_called[1]["count"],
            }

        return summary

    @classmethod
    def display_report(cls):
        """성능 보고서 표시 (DataFrame 활용)"""
        summary = cls.get_summary()
        if not summary:
            st.info("아직 수집된 성능 데이터가 없습니다")
            return

        st.markdown("### 📊 성능 보고서")

        # 요약 메트릭
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("총 함수", summary["total_functions"])

        with col2:
            st.metric("총 호출", summary["total_calls"])

        with col3:
            st.metric("총 시간", f"{summary['total_time']:.2f}s")

        with col4:
            st.metric("평균", f"{summary['avg_time']:.3f}s")

        # 에러가 있을 경우 추가 표시
        if summary["total_errors"] > 0:
            st.error(f"⚠️ 총 {summary['total_errors']}개의 에러가 발생했습니다")

        # 상세 메트릭 (DataFrame 표시)
        with st.expander("📈 상세 메트릭"):
            metrics = cls.get_metrics()
            if metrics:
                # DataFrame 생성
                rows = []
                for func_name, data in metrics.items():
                    avg_time = data["total_time"] / data["count"] if data["count"] > 0 else 0.0
                    rows.append({
                        "함수": func_name.split(".")[-1],  # 짧은 이름 표시
                        "모듈": func_name.rsplit(".", 1)[0] if "." in func_name else "-",
                        "호출 횟수": data["count"],
                        "평균(s)": round(avg_time, 3),
                        "최소(s)": round(data["min_time"], 3) if data["min_time"] != float("inf") else 0,
                        "최대(s)": round(data["max_time"], 3),
                        "총 시간(s)": round(data["total_time"], 3),
                        "에러": data["errors"],
                    })

                df = pd.DataFrame(rows)

                # 성능 기준으로 색상 적용 (조건부 서식)
                def highlight_slow(val, column):
                    if column == "평균(s)" and val > cls.SLOW_THRESHOLD:
                        return "background-color: #ffcccc"
                    if column == "최대(s)" and val > cls.CRITICAL_THRESHOLD:
                        return "background-color: #ff9999"
                    if column == "에러" and val > 0:
                        return "background-color: #ffcc99"
                    return ""

                # DataFrame 표시
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "호출 횟수": st.column_config.NumberColumn(format="%d"),
                        "평균(s)": st.column_config.NumberColumn(format="%.3f"),
                        "최소(s)": st.column_config.NumberColumn(format="%.3f"),
                        "최대(s)": st.column_config.NumberColumn(format="%.3f"),
                        "총 시간(s)": st.column_config.NumberColumn(format="%.3f"),
                        "에러": st.column_config.NumberColumn(format="%d"),
                    },
                )

                # 성능 인사이트
                st.markdown("#### 🔍 성능 인사이트")
                if summary["slowest_function"]:
                    st.warning(
                        f"가장 느린 실행: **{summary['slowest_function']['name']}** "
                        f"({summary['slowest_function']['time']:.2f}s)",
                    )
                if summary["most_called"]:
                    st.info(
                        f"가장 많이 호출: **{summary['most_called']['name']}** "
                        f"({summary['most_called']['count']}회)",
                    )
            else:
                st.caption("수집된 메트릭이 없습니다")

    @classmethod
    def reset_metrics(cls, show_message: bool = True):
        """메트릭 초기화 (UI 메시지 선택적)"""
        if "performance_metrics" in st.session_state:
            del st.session_state.performance_metrics

        if show_message:
            st.success("성능 메트릭이 초기화되었습니다")

    @classmethod
    def _is_debug_mode(cls) -> bool:
        """디버그 모드 확인 (세션 우선, 환경 변수 대체)"""
        try:
            # SessionManager 통합 (있으면 사용)
            from .session_manager import SessionManager
            return SessionManager.is_debug_mode()
        except ImportError:
            # SessionManager 없으면 환경 변수 사용
            return os.getenv("DEBUG_MODE", "").lower() in ["true", "1", "yes", "on"]


class Timer:
    """
    컨텍스트 매니저 타이머

    Usage:
        with Timer("데이터 로드"):
            # 시간을 측정할 코드
            load_data()

        # 조용히 측정만 하기
        with Timer("백그라운드 작업", show=False) as timer:
            process()
        print(f"실행 시간: {timer.duration:.3f}s")
    """

    def __init__(self, name: str = "Operation", show: bool = True):
        self.name = name
        self.show = show
        self.start_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.perf_counter()  # perf_counter로 변경
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.perf_counter() - self.start_time

        # 디버그 모드일 때만 표시 (정책 통일)
        if self.show and PerformanceMonitor._is_debug_mode():
            if self.duration > PerformanceMonitor.CRITICAL_THRESHOLD:
                st.error(f"⏱️ {self.name}: {self.duration:.2f}s (매우 느림!)")
            elif self.duration > PerformanceMonitor.SLOW_THRESHOLD:
                st.warning(f"⏱️ {self.name}: {self.duration:.2f}s (느림)")
            else:
                st.caption(f"⏱️ {self.name}: {self.duration:.3f}s")

        # 메트릭도 자동 저장
        PerformanceMonitor._store_metric(self.name, self.duration)

        # 에러가 발생했어도 False 반환하여 예외 전파
        return False


def benchmark(iterations: int = 100):
    """
    벤치마크 데코레이터 - 여러 번 실행하여 평균 성능 측정

    Usage:
        @benchmark(iterations=1000)
        def fast_function(x):
            return x * 2
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                result = func(*args, **kwargs)
                times.append(time.perf_counter() - start)

            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            # 결과 로깅
            PerformanceMonitor.logger.info(
                f"Benchmark {func.__name__}: "
                f"avg={avg_time * 1000:.3f}ms, "
                f"min={min_time * 1000:.3f}ms, "
                f"max={max_time * 1000:.3f}ms "
                f"({iterations} iterations)",
            )

            return result

        return wrapper
    return decorator
