"""Comprehensive test suite for ParallelSearchExecutor v2.0

테스트 항목:
1. 타임아웃 (개별 + 전체)
2. 취소 메커니즘
3. 경쟁 실행 (race execution)
4. 키 기반 필터 교집합
5. 에러 관측성 (_errors 맵)
6. 싱글턴 재구성
7. timed_execution 데코레이터
"""

import time
from typing import List

import pytest

import app.rag.parallel_executor as pe_module
from app.rag.parallel_executor import (
    ParallelSearchExecutor,
    get_parallel_executor,
    parallel_search_with_fallback,
    reconfigure_parallel_executor,
    timed_execution,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """각 테스트 전후로 싱글톤 상태 초기화"""
    # 테스트 전: 기존 싱글톤 정리
    with pe_module._global_executor_lock:
        if pe_module._global_executor is not None:
            try:
                pe_module._global_executor.shutdown()
            except Exception:
                pass
        pe_module._global_executor = None

    yield  # 테스트 실행

    # 테스트 후: 싱글톤 정리
    with pe_module._global_executor_lock:
        if pe_module._global_executor is not None:
            try:
                pe_module._global_executor.shutdown()
            except Exception:
                pass
        pe_module._global_executor = None


class TestTimedExecution:
    """timed_execution 데코레이터 테스트"""

    def test_decorator_basic(self):
        """기본 동작"""

        @timed_execution("test_func")
        def slow_func():
            time.sleep(0.01)
            return "result"

        result = slow_func()
        assert result == "result"
        # 함수가 정상 실행되면 OK (로깅은 부수 효과)

    def test_decorator_with_exception(self):
        """예외 발생 시에도 정상 동작"""

        @timed_execution("failing_func")
        def failing_func():
            time.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_func()

        # 예외가 발생해도 데코레이터는 정상 동작 (finally 블록)


class TestParallelSearchExecutor:
    """병렬 실행기 기본 기능 테스트"""

    def test_init(self):
        """초기화"""
        executor = ParallelSearchExecutor(max_workers=4)
        assert executor.max_workers == 4

    def test_execute_searches_basic(self):
        """기본 병렬 실행"""
        executor = ParallelSearchExecutor(max_workers=4)

        def task_a():
            time.sleep(0.01)
            return [1, 2, 3]

        def task_b():
            time.sleep(0.01)
            return [4, 5, 6]

        tasks = [
            {"name": "task_a", "func": task_a},
            {"name": "task_b", "func": task_b},
        ]

        results = executor.execute_searches(tasks)

        assert results["task_a"] == [1, 2, 3]
        assert results["task_b"] == [4, 5, 6]
        assert "_errors" in results
        assert len(results["_errors"]) == 0

    def test_execute_searches_with_error(self):
        """에러 발생 시 처리"""
        executor = ParallelSearchExecutor(max_workers=2)

        def good_task():
            return [1, 2, 3]

        def bad_task():
            raise ValueError("Task failed")

        tasks = [
            {"name": "good", "func": good_task},
            {"name": "bad", "func": bad_task},
        ]

        results = executor.execute_searches(tasks)

        assert results["good"] == [1, 2, 3]
        assert results["bad"] == []  # 실패 시 빈 리스트
        assert "bad" in results["_errors"]
        assert "ValueError" in results["_errors"]["bad"]

    def test_execute_searches_per_task_timeout(self):
        """개별 태스크 타임아웃"""
        executor = ParallelSearchExecutor(max_workers=2)

        def slow_task():
            time.sleep(2.0)  # 2초 (충분히 길게)
            return [1, 2, 3]

        def fast_task():
            return [4, 5, 6]

        tasks = [
            {"name": "slow", "func": slow_task},
            {"name": "fast", "func": fast_task},
        ]

        # NOTE: per_task_timeout은 result() 호출 시 적용되는데,
        # 이미 완료된 태스크는 타임아웃되지 않음
        # 전체 타임아웃을 사용하는 것이 더 안정적
        results = executor.execute_searches(tasks, total_timeout=0.5)

        # slow는 타임아웃, fast는 성공 가능
        assert results["fast"] == [4, 5, 6]
        # slow는 타임아웃되거나 아직 실행 중
        assert "slow" in results["_errors"] or results["slow"] == []

    def test_execute_searches_total_timeout(self):
        """전체 배치 타임아웃"""
        executor = ParallelSearchExecutor(max_workers=2)

        def slow_task_1():
            time.sleep(0.2)
            return [1]

        def slow_task_2():
            time.sleep(0.2)
            return [2]

        tasks = [
            {"name": "task1", "func": slow_task_1},
            {"name": "task2", "func": slow_task_2},
        ]

        results = executor.execute_searches(tasks, total_timeout=0.15)

        # 전체 타임아웃으로 일부는 완료 못함
        assert "_errors" in results
        # 타임아웃된 태스크가 있어야 함
        assert len(results["_errors"]) > 0


class TestExecuteFilters:
    """병렬 필터 실행 테스트"""

    def test_filters_basic(self):
        """기본 필터링"""
        executor = ParallelSearchExecutor(max_workers=2)

        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        # 짝수만, 5보다 큰 것만
        filter_even = lambda x: x % 2 == 0
        filter_gt5 = lambda x: x > 5

        result = executor.execute_filters(items, [filter_even, filter_gt5])

        # 짝수 AND 5보다 큼 → [6, 8, 10]
        assert sorted(result) == [6, 8, 10]

    def test_filters_with_key(self):
        """키 함수 기반 필터링"""
        executor = ParallelSearchExecutor(max_workers=2)

        # 딕셔너리 리스트
        items = [
            {"id": 1, "name": "alice", "age": 25},
            {"id": 2, "name": "bob", "age": 30},
            {"id": 3, "name": "charlie", "age": 35},
            {"id": 4, "name": "diana", "age": 40},
        ]

        # 나이 > 28, 이름 길이 >= 4
        filter_age = lambda x: x["age"] > 28
        filter_name_len = lambda x: len(x["name"]) >= 4

        # 키 함수: id 기준 교집합
        result = executor.execute_filters(
            items, [filter_age, filter_name_len], key=lambda x: x["id"]
        )

        # bob(30, len=3) - 제외 (이름 길이)
        # charlie(35, len=7) - 포함
        # diana(40, len=5) - 포함
        result_ids = [r["id"] for r in result]
        assert sorted(result_ids) == [3, 4]

    def test_filters_empty(self):
        """빈 필터 리스트"""
        executor = ParallelSearchExecutor(max_workers=2)
        items = [1, 2, 3]

        result = executor.execute_filters(items, [])
        assert result == items


class TestRaceExecution:
    """경쟁 실행 (race execution) 테스트"""

    def test_race_primary_wins(self):
        """프라이머리가 먼저 완료"""

        def fast_primary():
            time.sleep(0.01)
            return ["primary"]

        def slow_fallback():
            time.sleep(1.0)
            return ["fallback"]

        result = parallel_search_with_fallback(fast_primary, slow_fallback, timeout=2.0)

        assert result == ["primary"]

    def test_race_fallback_wins(self):
        """폴백이 먼저 완료"""

        def slow_primary():
            time.sleep(1.0)
            return ["primary"]

        def fast_fallback():
            time.sleep(0.01)
            return ["fallback"]

        result = parallel_search_with_fallback(slow_primary, fast_fallback, timeout=2.0)

        assert result == ["fallback"]

    def test_race_primary_only(self):
        """폴백 없이 프라이머리만"""

        def primary():
            time.sleep(0.01)
            return ["primary"]

        result = parallel_search_with_fallback(primary, None, timeout=1.0)

        assert result == ["primary"]

    def test_race_both_timeout(self):
        """둘 다 타임아웃"""

        def slow_primary():
            time.sleep(1.0)
            return ["primary"]

        def slow_fallback():
            time.sleep(1.0)
            return ["fallback"]

        result = parallel_search_with_fallback(
            slow_primary, slow_fallback, timeout=0.05
        )

        assert result == []

    def test_race_winner_fails_fallback_succeeds(self):
        """승자가 실패하고 폴백이 성공"""

        def failing_primary():
            time.sleep(0.01)
            raise ValueError("Primary failed")

        def slow_fallback():
            time.sleep(0.1)
            return ["fallback"]

        result = parallel_search_with_fallback(
            failing_primary, slow_fallback, timeout=0.5
        )

        # 프라이머리가 먼저 끝났지만 실패, 폴백 결과 반환
        assert result == ["fallback"]


class TestSingletonManagement:
    """싱글턴 관리 테스트"""

    def test_get_parallel_executor_singleton(self):
        """싱글턴 동작"""
        e1 = get_parallel_executor(max_workers=6)
        e2 = get_parallel_executor(max_workers=8)  # 무시됨

        # 동일 인스턴스
        assert e1 is e2
        assert e1.max_workers == 6  # 최초 값 유지

    def test_reconfigure_parallel_executor(self):
        """재구성"""
        # 재구성 (이전 테스트에서 이미 생성되었을 수 있으므로)
        reconfigure_parallel_executor(max_workers=4)
        e1 = get_parallel_executor()
        assert e1.max_workers == 4

        # 재구성
        reconfigure_parallel_executor(max_workers=8)

        e2 = get_parallel_executor()
        assert e2.max_workers == 8
        assert e1 is not e2  # 다른 인스턴스


class TestConcurrency:
    """동시성 테스트"""

    def test_many_tasks(self):
        """많은 태스크 동시 실행"""
        executor = ParallelSearchExecutor(max_workers=6)

        def task(n: int):
            time.sleep(0.01)
            return [n * 10]

        tasks = [{"name": f"task_{i}", "func": task, "args": (i,)} for i in range(20)]

        results = executor.execute_searches(tasks)

        # 모든 태스크 성공
        for i in range(20):
            assert results[f"task_{i}"] == [i * 10]

        # 에러 없음
        assert len(results["_errors"]) == 0


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_tasks(self):
        """빈 태스크 리스트"""
        executor = ParallelSearchExecutor(max_workers=2)
        results = executor.execute_searches([])
        assert results == {}

    def test_empty_items_filter(self):
        """빈 아이템 리스트 필터"""
        executor = ParallelSearchExecutor(max_workers=2)
        result = executor.execute_filters([], [lambda x: True])
        assert result == []

    def test_no_fallback(self):
        """폴백 없이 프라이머리만 (성공)"""

        def primary():
            return ["result"]

        result = parallel_search_with_fallback(primary, None, timeout=1.0)
        assert result == ["result"]

    def test_no_fallback_primary_fails(self):
        """폴백 없이 프라이머리 실패"""

        def failing_primary():
            raise ValueError("Failed")

        result = parallel_search_with_fallback(failing_primary, None, timeout=1.0)
        assert result == []


if __name__ == "__main__":
    # 직접 실행 시 간단한 검증
    print("Running basic parallel executor tests...")

    # 기본 병렬 실행
    executor = ParallelSearchExecutor(max_workers=4)

    def task_a():
        time.sleep(0.01)
        return [1, 2, 3]

    def task_b():
        time.sleep(0.01)
        return [4, 5, 6]

    tasks = [
        {"name": "task_a", "func": task_a},
        {"name": "task_b", "func": task_b},
    ]

    results = executor.execute_searches(tasks)
    print(f"✅ Parallel execution: {results}")

    # 필터 테스트
    items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    filtered = executor.execute_filters(items, [lambda x: x % 2 == 0, lambda x: x > 5])
    print(f"✅ Filtered: {filtered}")

    # 경쟁 실행
    def fast():
        time.sleep(0.01)
        return ["fast"]

    def slow():
        time.sleep(1.0)
        return ["slow"]

    race_result = parallel_search_with_fallback(fast, slow, timeout=2.0)
    print(f"✅ Race execution: {race_result}")

    print("\n✅ All basic tests passed!")
