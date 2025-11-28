#!/usr/bin/env python3
"""Parallel Execution Utilities v2.0 for RAG System

2025-11-11 v2.0 개선사항:
- 정밀 타이밍: perf_counter_ns() + 예외 안전
- 타임아웃/취소: 전체+개별 타임아웃, 취소 시그널 전파
- 에러 관측성: _errors 맵 반환
- 키 기반 교집합: 값 비교로 정확도 향상
- 경쟁 실행: 프라이머리/폴백 동시 실행 후 승자 채택
- 싱글턴 관리: 재구성 API + atexit 등록
"""
import atexit
import logging
import threading
import time
from collections.abc import Callable, Hashable
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
from concurrent.futures import (
    TimeoutError as FuturesTimeout,
)
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)


def timed_execution(func_name: str, level: int = logging.DEBUG):
    """Decorator to log execution time with exception safety

    Args:
        func_name: 함수 이름 (로그용)
        level: 로그 레벨 (기본 DEBUG)

    Returns:
        Decorated function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter_ns()
            try:
                return func(*args, **kwargs)
            finally:
                dt_ms = (time.perf_counter_ns() - t0) / 1_000_000
                logger.log(level, f"⏱ {func_name} took {dt_ms:.3f} ms")

        return wrapper

    return decorator


class ParallelSearchExecutor:
    """Execute multiple search operations in parallel v2.0"""

    def __init__(self, max_workers: int = 6):
        """Initialize parallel executor

        Args:
            max_workers: Maximum number of parallel threads (default 6)
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def execute_searches(
        self,
        search_tasks: list[dict[str, Any]],
        per_task_timeout: Optional[float] = None,
        total_timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """Execute multiple search tasks in parallel with timeout support

        Args:
            search_tasks: List of search task dictionaries:
                [
                    {
                        "name": "bm25_search",
                        "func": callable,
                        "args": tuple,
                        "kwargs": dict
                    },
                    ...
                ]
            per_task_timeout: 개별 태스크 타임아웃 (초)
            total_timeout: 전체 배치 타임아웃 (초)

        Returns:
            Dict mapping task names to results:
            {
                "bm25_search": [...],
                "vector_search": [...],
                "_errors": {"task_name": "error_msg", ...}
            }
        """
        if not search_tasks:
            return {}

        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        futures = {}
        t0 = time.perf_counter_ns()

        # Submit all tasks
        for task in search_tasks:
            name = task["name"]
            func = task["func"]
            args = task.get("args", ())
            kwargs = task.get("kwargs", {})

            future = self.executor.submit(func, *args, **kwargs)
            futures[future] = name
            logger.debug(f"🚀 Submitted: {name}")

        done = set()
        try:
            while len(done) < len(futures):
                # 전체 타임박스 체크
                if total_timeout is not None:
                    elapsed_sec = (time.perf_counter_ns() - t0) / 1_000_000_000
                    remaining = max(0.0, total_timeout - elapsed_sec)
                    if remaining == 0.0:
                        raise FuturesTimeout("total timeout exceeded")
                else:
                    remaining = None

                # 완료 대기
                pending_futures = [f for f in futures if f not in done]
                for fut in as_completed(pending_futures, timeout=remaining):
                    name = futures[fut]
                    try:
                        res = fut.result(timeout=per_task_timeout)
                        results[name] = res
                        logger.debug(f"✅ Done: {name}")
                    except Exception as e:
                        errors[name] = repr(e)
                        logger.error(f"❌ Failed: {name} - {e}")
                        results[name] = []
                    finally:
                        done.add(fut)

        except FuturesTimeout:
            # 남은 작업 취소 시도
            for fut in futures:
                if fut not in done:
                    fut.cancel()
                    name = futures[fut]
                    errors[name] = "Timeout"
                    results[name] = []
            logger.warning("⏳ Parallel batch timed out")

        total_ms = (time.perf_counter_ns() - t0) / 1_000_000
        logger.info(f"🏁 All tasks finished in {total_ms:.3f} ms")

        # 에러 맵 추가
        results["_errors"] = errors
        return results

    def execute_filters(
        self,
        items: list[Any],
        filter_funcs: list[Callable[[Any], bool]],
        key: Optional[Callable[[Any], Hashable]] = None,
    ) -> list[Any]:
        """Apply multiple filter functions in parallel with key-based intersection

        Args:
            items: List of items to filter
            filter_funcs: List of filter functions (each returns bool)
            key: Key function for intersection (default: identity)

        Returns:
            List of items that passed ALL filters
        """
        if not filter_funcs or not items:
            return items

        # 키 함수 기본값: identity
        key_fn = key or (lambda x: x)

        # Execute filters in parallel
        futures = {}
        for i, filter_func in enumerate(filter_funcs):

            def apply_filter(func, data, keyfn):
                return [keyfn(it) for it in data if func(it)]

            future = self.executor.submit(apply_filter, filter_func, items, key_fn)
            futures[future] = f"filter_{i}"

        # Collect filtered results
        result_sets: list[set] = []
        for future in as_completed(futures):
            try:
                result = future.result()
                result_sets.append(set(result))
            except Exception as e:
                name = futures[future]
                logger.error(f"❌ Filter failed: {name} - {e}")

        # Intersection of all filter results
        if not result_sets:
            return items

        intersection = set.intersection(*result_sets)
        return [it for it in items if key_fn(it) in intersection]

    def shutdown(self):
        """Shutdown the thread pool executor"""
        self.executor.shutdown(wait=True)
        logger.info("🔄 Parallel executor shutdown")


# Global executor instance with lock
_global_executor: Optional[ParallelSearchExecutor] = None
_global_executor_lock = threading.Lock()


def get_parallel_executor(max_workers: int = 6) -> ParallelSearchExecutor:
    """Get or create global parallel executor instance (thread-safe singleton)

    Args:
        max_workers: Maximum number of parallel threads (default 6)

    Returns:
        ParallelSearchExecutor instance
    """
    global _global_executor
    with _global_executor_lock:
        if _global_executor is None:
            _global_executor = ParallelSearchExecutor(max_workers=max_workers)
            atexit.register(lambda: _global_executor.shutdown())
            logger.info(
                f"✅ Global parallel executor initialized (max_workers={max_workers})",
            )
    return _global_executor


def reconfigure_parallel_executor(max_workers: int) -> None:
    """Reconfigure global executor with new max_workers

    Args:
        max_workers: New maximum number of parallel threads
    """
    global _global_executor
    with _global_executor_lock:
        if _global_executor is not None:
            _global_executor.shutdown()
        _global_executor = ParallelSearchExecutor(max_workers=max_workers)
        atexit.register(lambda: _global_executor.shutdown())
        logger.info(f"🔧 Reconfigured executor (max_workers={max_workers})")


def parallel_search_with_fallback(
    primary_search: Callable,
    fallback_search: Optional[Callable] = None,
    timeout: float = 5.0,
) -> Any:
    """Execute search with race execution: primary + fallback simultaneously

    프라이머리와 폴백을 동시 실행하고, 먼저 완료된 결과를 채택.
    승자 외 나머지는 취소 시도.

    Args:
        primary_search: Primary search function
        fallback_search: Fallback search function (optional)
        timeout: Timeout in seconds

    Returns:
        Search results from first-completed (primary or fallback)
    """
    executor = get_parallel_executor()
    futures = [executor.executor.submit(primary_search)]
    labels = ["primary"]

    if fallback_search:
        futures.append(executor.executor.submit(fallback_search))
        labels.append("fallback")

    # 경쟁 실행: 먼저 끝난 것 채택
    done, pending = wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)

    if not done:
        # 타임아웃: 모든 작업 취소
        for f in futures:
            f.cancel()
        logger.warning("⏳ Both searches timed out")
        return []

    # 승자 결과 가져오기
    winner = next(iter(done))
    winner_label = labels[futures.index(winner)]

    try:
        result = winner.result()
        logger.debug(f"🏆 Winner: {winner_label}")
    except Exception as e:
        logger.warning(f"⚠️ Winner ({winner_label}) failed: {e}")
        # 승자가 실패했으면, 대기 중인 작업 결과 시도
        for p in pending:
            try:
                fallback_result = p.result(timeout=timeout)
                logger.info("🔄 Fallback succeeded after primary failure")
                return fallback_result or []
            except Exception as e2:
                logger.error(f"❌ Fallback also failed: {e2}")
                return []
        return []

    # 패자 취소 시도
    for p in pending:
        cancelled = p.cancel()
        if cancelled:
            logger.debug("🚫 Cancelled pending search")

    return result or []
