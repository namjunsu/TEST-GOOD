#!/usr/bin/env python3
"""
Parallel Execution Utilities for RAG System
Enables concurrent execution of search operations for improved performance
"""
import time
import logging
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

logger = logging.getLogger(__name__)


def timed_execution(func_name: str):
    """Decorator to log execution time"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            logger.debug(f"⏱️ {func_name} took {elapsed:.3f}s")
            return result
        return wrapper
    return decorator


class ParallelSearchExecutor:
    """Execute multiple search operations in parallel"""

    def __init__(self, max_workers: int = 3):
        """
        Initialize parallel executor

        Args:
            max_workers: Maximum number of parallel threads (default 3)
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def execute_searches(
        self,
        search_tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute multiple search tasks in parallel

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

        Returns:
            Dict mapping task names to results:
            {
                "bm25_search": [...],
                "vector_search": [...],
                ...
            }
        """
        if not search_tasks:
            return {}

        results = {}
        futures = {}

        # Submit all tasks
        for task in search_tasks:
            name = task["name"]
            func = task["func"]
            args = task.get("args", ())
            kwargs = task.get("kwargs", {})

            future = self.executor.submit(func, *args, **kwargs)
            futures[future] = name
            logger.debug(f"🚀 Submitted parallel task: {name}")

        # Collect results as they complete
        start_time = time.time()
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results[name] = result
                elapsed = time.time() - start_time
                logger.info(f"✅ Parallel task completed: {name} ({elapsed:.3f}s)")
            except Exception as e:
                logger.error(f"❌ Parallel task failed: {name} - {e}")
                results[name] = []  # Return empty result on error

        total_time = time.time() - start_time
        logger.info(f"🏁 All parallel tasks completed in {total_time:.3f}s")

        return results

    def execute_filters(
        self,
        items: List[Any],
        filter_funcs: List[Callable[[Any], bool]]
    ) -> List[Any]:
        """
        Apply multiple filter functions in parallel

        Args:
            items: List of items to filter
            filter_funcs: List of filter functions (each returns bool)

        Returns:
            List of items that passed ALL filters
        """
        if not filter_funcs or not items:
            return items

        # Execute filters in parallel
        futures = {}
        for i, filter_func in enumerate(filter_funcs):
            future = self.executor.submit(
                lambda func, data: [item for item in data if func(item)],
                filter_func,
                items
            )
            futures[future] = f"filter_{i}"

        # Collect filtered results
        filtered_results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                filtered_results.append(result)
            except Exception as e:
                name = futures[future]
                logger.error(f"❌ Filter failed: {name} - {e}")

        # Intersection of all filter results
        if not filtered_results:
            return items

        # Find items that appear in ALL filter results
        final_items = set(id(item) for item in filtered_results[0])
        for result in filtered_results[1:]:
            final_items &= set(id(item) for item in result)

        return [item for item in items if id(item) in final_items]

    def shutdown(self):
        """Shutdown the thread pool executor"""
        self.executor.shutdown(wait=True)
        logger.info("🔄 Parallel executor shutdown")


# Global executor instance
_global_executor: Optional[ParallelSearchExecutor] = None


def get_parallel_executor(max_workers: int = 3) -> ParallelSearchExecutor:
    """
    Get or create global parallel executor instance

    Args:
        max_workers: Maximum number of parallel threads

    Returns:
        ParallelSearchExecutor instance
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = ParallelSearchExecutor(max_workers=max_workers)
        logger.info(f"✅ Global parallel executor initialized (max_workers={max_workers})")
    return _global_executor


def parallel_search_with_fallback(
    primary_search: Callable,
    fallback_search: Optional[Callable] = None,
    timeout: float = 5.0
) -> Any:
    """
    Execute search with fallback if primary fails or times out

    Args:
        primary_search: Primary search function
        fallback_search: Fallback search function (optional)
        timeout: Timeout in seconds

    Returns:
        Search results from primary or fallback
    """
    executor = get_parallel_executor()

    # Submit primary search
    future = executor.executor.submit(primary_search)

    try:
        result = future.result(timeout=timeout)
        if result:
            return result
    except Exception as e:
        logger.warning(f"⚠️ Primary search failed: {e}")

    # Fallback if primary failed
    if fallback_search:
        logger.info("🔄 Using fallback search")
        try:
            return fallback_search()
        except Exception as e:
            logger.error(f"❌ Fallback search also failed: {e}")
            return []

    return []
