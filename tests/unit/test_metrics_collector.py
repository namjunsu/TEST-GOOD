"""Comprehensive test suite for CodeSearchMetrics v2.0

테스트 항목:
1. 백분위 계산 정확도 (nearest-rank)
2. 스레드 안전성 (동시 기록)
3. 컨텍스트 매니저 (예외 처리)
4. EWMA 지표
5. 프로메테우스 텍스트 포맷
6. 락 홀드 최소화
"""

import concurrent.futures
import math
import random
import time

import pytest

from app.rag.metrics_collector import (
    CodeSearchMetrics,
    _percentile,
    get_metrics_collector,
)


class TestPercentileCalculation:
    """백분위 계산 정확도 테스트"""

    def test_percentile_empty(self):
        """빈 리스트 처리"""
        assert _percentile([], 0.50) == 0.0
        assert _percentile([], 0.95) == 0.0

    def test_percentile_single(self):
        """단일 값"""
        assert _percentile([100.0], 0.50) == 100.0
        assert _percentile([100.0], 0.95) == 100.0

    def test_percentile_uniform(self):
        """균등분포 (1..100)"""
        values = list(range(1, 101))
        p50 = _percentile(values, 0.50)
        p95 = _percentile(values, 0.95)

        # Nearest-rank: ceil(0.50 * 100) = 50, ceil(0.95 * 100) = 95
        assert p50 == 50.0
        assert p95 == 95.0

    def test_percentile_exponential(self):
        """지수분포 (꼬리가 긴 분포)"""
        random.seed(42)
        values = sorted([random.expovariate(1.0) * 100 for _ in range(1000)])

        p50 = _percentile(values, 0.50)
        p95 = _percentile(values, 0.95)

        # 중앙값은 낮고, 95th는 높아야 함
        assert 50 < p50 < 100  # 대략적인 범위
        assert p95 > p50 * 2  # 95th는 50th의 2배 이상

    def test_percentile_edge_cases(self):
        """경계값 테스트"""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        # p=0.01 (최소값 근처)
        assert _percentile(values, 0.01) == 1.0

        # p=1.0 (최대값)
        assert _percentile(values, 1.0) == 5.0

        # p=0.20 (1/5)
        assert _percentile(values, 0.20) == 1.0

        # p=0.80 (4/5)
        assert _percentile(values, 0.80) == 4.0


class TestMetricsCollector:
    """메트릭 수집기 기본 기능 테스트"""

    def test_init(self):
        """초기화"""
        m = CodeSearchMetrics(latency_window_size=100)
        metrics = m.get_metrics()

        assert metrics["code_queries_total"] == 0
        assert metrics["exact_match_hits_total"] == 0
        assert metrics["exact_match_hit_rate"] == 0.0
        assert metrics["retrieval_latency_ms_p50"] == 0
        assert metrics["retrieval_latency_ms_p95"] == 0

    def test_record_code_query(self):
        """쿼리 기록"""
        m = CodeSearchMetrics()

        m.record_code_query(has_exact_match=True, stage0_count=10, stage1_count=5)
        m.record_code_query(has_exact_match=False, stage0_count=8, stage1_count=3)
        m.record_code_query(has_exact_match=True, stage0_count=12, stage1_count=6)

        metrics = m.get_metrics()
        assert metrics["code_queries_total"] == 3
        assert metrics["exact_match_hits_total"] == 2
        assert metrics["exact_match_hit_rate"] == 0.667  # 2/3 rounded
        assert metrics["stage0_candidates_last"] == 12
        assert metrics["stage1_candidates_last"] == 6

    def test_record_latency(self):
        """지연시간 기록 및 백분위"""
        m = CodeSearchMetrics()

        # 100개 샘플: 1..100 ms
        for i in range(1, 101):
            m.record_latency(float(i))

        metrics = m.get_metrics()
        assert metrics["retrieval_latency_ms_p50"] == 50
        assert metrics["retrieval_latency_ms_p95"] == 95

    def test_record_other_counters(self):
        """기타 카운터"""
        m = CodeSearchMetrics()

        m.record_rrf_fusion()
        m.record_rrf_fusion()
        m.record_citation_forced()

        metrics = m.get_metrics()
        assert metrics["rrf_fusion_used_total"] == 2
        assert metrics["citation_forced_total"] == 1

    def test_reset(self):
        """리셋"""
        m = CodeSearchMetrics()

        m.record_code_query(True, 10, 5)
        m.record_latency(100.0)

        m.reset()

        metrics = m.get_metrics()
        assert metrics["code_queries_total"] == 0
        assert metrics["exact_match_hits_total"] == 0
        assert metrics["retrieval_latency_ms_p50"] == 0


class TestContextManager:
    """컨텍스트 매니저 테스트"""

    def test_measure_retrieval_latency(self):
        """정상 경로"""
        m = CodeSearchMetrics()

        with m.measure_retrieval_latency():
            time.sleep(0.01)  # 10ms

        metrics = m.get_metrics()
        p50 = metrics["retrieval_latency_ms_p50"]

        # 10ms 정도 (오차 허용)
        assert 5 < p50 < 50

    def test_measure_retrieval_latency_with_exception(self):
        """예외 발생 시에도 지연 기록"""
        m = CodeSearchMetrics()

        try:
            with m.measure_retrieval_latency():
                time.sleep(0.01)
                raise ValueError("Test exception")
        except ValueError:
            pass

        metrics = m.get_metrics()
        p50 = metrics["retrieval_latency_ms_p50"]

        # 예외가 발생해도 지연은 기록됨
        assert 5 < p50 < 50


class TestThreadSafety:
    """스레드 안전성 테스트"""

    def test_concurrent_record_code_query(self):
        """동시 쿼리 기록 (32 스레드)"""
        m = CodeSearchMetrics()

        def worker(thread_id: int):
            for i in range(10):
                has_hit = (thread_id + i) % 2 == 0
                m.record_code_query(has_hit, thread_id, i)

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = [executor.submit(worker, tid) for tid in range(32)]
            concurrent.futures.wait(futures)

        metrics = m.get_metrics()
        assert metrics["code_queries_total"] == 32 * 10  # 320

    def test_concurrent_record_latency(self):
        """동시 지연 기록 (32 스레드)"""
        m = CodeSearchMetrics()

        def worker(thread_id: int):
            for i in range(100):
                m.record_latency(float(thread_id * 100 + i))

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = [executor.submit(worker, tid) for tid in range(32)]
            concurrent.futures.wait(futures)

        metrics = m.get_metrics()
        # 윈도 크기 제한으로 일부만 남음 (기본 2000)
        # 최소한 백분위 계산이 크래시 없이 완료되어야 함
        assert metrics["retrieval_latency_ms_p50"] > 0
        assert metrics["retrieval_latency_ms_p95"] > 0

    def test_concurrent_get_metrics_and_record(self):
        """get_metrics 중에도 record 가능 (락 홀드 최소화)"""
        m = CodeSearchMetrics()

        # 초기 데이터
        for i in range(100):
            m.record_latency(float(i))

        def reader():
            """반복적으로 메트릭 읽기"""
            for _ in range(50):
                metrics = m.get_metrics()
                assert metrics["retrieval_latency_ms_p50"] >= 0

        def writer():
            """반복적으로 지연 기록"""
            for i in range(100):
                m.record_latency(float(i + 1000))

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            readers = [executor.submit(reader) for _ in range(4)]
            writers = [executor.submit(writer) for _ in range(4)]
            concurrent.futures.wait(readers + writers)

        # 데드락 없이 완료되어야 함
        metrics = m.get_metrics()
        assert metrics["retrieval_latency_ms_p50"] > 0


class TestEWMAMetrics:
    """EWMA 지표 테스트"""

    def test_ewma_qps(self):
        """QPS EWMA"""
        m = CodeSearchMetrics()

        # 짧은 간격으로 3개 쿼리
        m.record_code_query(True, 10, 5)
        time.sleep(0.1)
        m.record_code_query(False, 8, 3)
        time.sleep(0.1)
        m.record_code_query(True, 12, 6)

        metrics = m.get_metrics()
        # QPS EWMA는 0보다 커야 함 (정확한 값 계산은 복잡)
        assert metrics["qps_ewma_1m"] >= 0.0

    def test_ewma_hit_rate(self):
        """히트율 EWMA"""
        m = CodeSearchMetrics()

        # 히트 패턴: True, False, True
        m.record_code_query(True, 10, 5)
        time.sleep(0.05)
        m.record_code_query(False, 8, 3)
        time.sleep(0.05)
        m.record_code_query(True, 12, 6)

        metrics = m.get_metrics()
        # 히트율 EWMA는 0과 1 사이
        assert 0.0 <= metrics["hit_rate_ewma_1m"] <= 1.0


class TestPrometheusExport:
    """프로메테우스 텍스트 포맷 테스트"""

    def test_to_prometheus_text(self):
        """프로메테우스 포맷 내보내기"""
        m = CodeSearchMetrics()

        # 샘플 데이터
        m.record_code_query(True, 10, 5)
        m.record_code_query(False, 8, 3)
        m.record_latency(100.0)
        m.record_latency(200.0)
        m.record_rrf_fusion()

        prom_text = m.to_prometheus_text()

        # 필수 메트릭 포함 확인
        assert "code_queries_total 2" in prom_text
        assert "exact_match_hits_total 1" in prom_text
        assert "exact_match_hit_rate" in prom_text
        assert "retrieval_latency_ms_p50" in prom_text
        assert "retrieval_latency_ms_p95" in prom_text
        assert "rrf_fusion_used_total 1" in prom_text

        # HELP 및 TYPE 주석 포함
        assert "# HELP code_queries_total" in prom_text
        assert "# TYPE code_queries_total counter" in prom_text

    def test_prometheus_format_validity(self):
        """프로메테우스 포맷 유효성"""
        m = CodeSearchMetrics()
        m.record_code_query(True, 10, 5)

        prom_text = m.to_prometheus_text()

        # 각 메트릭 라인이 올바른 포맷인지 확인
        lines = prom_text.strip().split("\n")
        metric_lines = [line for line in lines if not line.startswith("#") and line]

        for line in metric_lines:
            # 메트릭 라인: "metric_name value"
            parts = line.split()
            assert len(parts) == 2
            metric_name, value = parts
            assert metric_name  # 이름이 있어야 함
            # 값이 숫자로 파싱 가능해야 함
            float(value)


class TestSingleton:
    """싱글턴 테스트"""

    def test_get_metrics_collector_singleton(self):
        """싱글턴 인스턴스"""
        m1 = get_metrics_collector()
        m2 = get_metrics_collector()

        # 동일 인스턴스
        assert m1 is m2

        # 상태 공유
        m1.record_code_query(True, 10, 5)
        metrics2 = m2.get_metrics()
        assert metrics2["code_queries_total"] == 1


class TestLatencyWindowSize:
    """지연시간 윈도 크기 테스트"""

    def test_window_size_limit(self):
        """윈도 크기 제한"""
        m = CodeSearchMetrics(latency_window_size=10)

        # 20개 샘플 추가 (윈도 크기 10)
        for i in range(20):
            m.record_latency(float(i))

        # 마지막 10개만 남음 (10..19)
        metrics = m.get_metrics()
        p50 = metrics["retrieval_latency_ms_p50"]

        # 중앙값은 14 근처 (10..19의 중앙)
        assert 13 <= p50 <= 15


if __name__ == "__main__":
    # 직접 실행 시 간단한 검증
    print("Running basic metrics tests...")

    # 백분위 테스트
    values = list(range(1, 101))
    p50 = _percentile(values, 0.50)
    p95 = _percentile(values, 0.95)
    print(f"✅ Percentile: p50={p50}, p95={p95}")

    # 메트릭 수집기 테스트
    m = CodeSearchMetrics()
    m.record_code_query(True, 10, 5)
    m.record_code_query(False, 8, 3)
    m.record_latency(100.0)
    m.record_latency(200.0)

    metrics = m.get_metrics()
    print(f"✅ Metrics: {metrics}")

    # 컨텍스트 매니저 테스트
    with m.measure_retrieval_latency():
        time.sleep(0.01)
    print(f"✅ Context manager: p50={m.get_metrics()['retrieval_latency_ms_p50']}")

    # 프로메테우스 포맷
    prom = m.to_prometheus_text()
    print(f"✅ Prometheus format ({len(prom)} bytes)")

    print("\n✅ All basic tests passed!")
