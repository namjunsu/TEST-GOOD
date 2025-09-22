"""
Performance Profiler
코드 성능 프로파일링
"""

import cProfile
import pstats
import io
from contextlib import contextmanager
import time
from functools import wraps
from typing import Callable, Any

class PerformanceProfiler:
    """성능 프로파일러"""

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.timings = {}

    @contextmanager
    def profile_block(self, name: str):
        """코드 블록 프로파일링"""
        start_time = time.perf_counter()

        self.profiler.enable()
        try:
            yield
        finally:
            self.profiler.disable()
            elapsed = time.perf_counter() - start_time

            # 타이밍 기록
            if name not in self.timings:
                self.timings[name] = []
            self.timings[name].append(elapsed)

            print(f"⏱️ {name}: {elapsed*1000:.2f}ms")

    def profile_function(self, func: Callable) -> Callable:
        """함수 프로파일링 데코레이터"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.profile_block(func.__name__):
                return func(*args, **kwargs)
        return wrapper

    def get_stats(self, top_n: int = 10) -> str:
        """프로파일링 통계"""
        s = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=s)
        stats.sort_stats('cumulative')
        stats.print_stats(top_n)
        return s.getvalue()

    def get_timing_report(self) -> Dict:
        """타이밍 리포트"""
        report = {}
        for name, times in self.timings.items():
            report[name] = {
                'count': len(times),
                'total_ms': sum(times) * 1000,
                'avg_ms': (sum(times) / len(times)) * 1000 if times else 0,
                'min_ms': min(times) * 1000 if times else 0,
                'max_ms': max(times) * 1000 if times else 0
            }
        return report

# 전역 프로파일러
profiler = PerformanceProfiler()

# 사용 예시 데코레이터
def measure_performance(func):
    """성능 측정 데코레이터"""
    return profiler.profile_function(func)
