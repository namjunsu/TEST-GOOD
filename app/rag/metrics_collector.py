"""RAG 코드 검색 메트릭 수집기 v2.0 (Thread-safe + High precision)

전역 싱글턴으로 동작하며, HybridRetriever/ExactMatchRetriever에서 호출

2025-11-11 v2.0 개선사항:
- Nearest-rank 백분위 계산 (정확도 향상)
- 락 홀드 최소화 (스냅샷 후 계산)
- 단조 시계 사용 (시계 변경 차단)
- 컨텍스트 매니저 API (측정 코드 표준화)
- EWMA 지표 (처리율/히트율 추세)
- 프로메테우스 텍스트 포맷 내보내기
"""

import math
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.logging import get_logger

logger = get_logger(__name__)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """최근접 순위(nearest-rank) 백분위 계산

    Args:
        sorted_vals: 정렬된 샘플 리스트
        p: 백분위 (0.0 < p <= 1.0)

    Returns:
        p번째 백분위 값
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    # 최근접 순위: ceil(p * n), 범위 [1, n]
    rank = max(1, min(n, math.ceil(p * n)))
    return float(sorted_vals[rank - 1])


class CodeSearchMetrics:
    """코드 검색 메트릭 수집기 v2.0 (Thread-safe + High precision)"""

    def __init__(self, latency_window_size: int = 2000):
        """Initialize metrics collector

        Args:
            latency_window_size: 지연시간 샘플 윈도 크기 (기본 2000)
        """
        self._lock = threading.Lock()

        # 카운터
        self.code_queries_total = 0
        self.exact_match_hits_total = 0
        self.rrf_fusion_used_total = 0
        self.citation_forced_total = 0

        # 마지막 검색 상태
        self.stage0_candidates_last = 0
        self.stage1_candidates_last = 0

        # 지연시간 히스토그램 (최근 N개, 정확한 백분위 계산용)
        self.latency_samples = deque(maxlen=latency_window_size)

        # EWMA 지표 (1분 반감기)
        self._last_tick = time.perf_counter()
        self._qps_ewma_1m = 0.0  # 초당 쿼리 수
        self._hit_rate_ewma_1m = 0.0  # 히트율 추세

    def _tick_rate(self, hit_increment: int) -> None:
        """처리율 및 히트율 EWMA 갱신 (내부용, 락 내부에서 호출)

        Args:
            hit_increment: 히트 증분 (0 또는 1)
        """
        now = time.perf_counter()
        dt = max(1e-6, now - self._last_tick)

        # 순간 처리율 (호출당)
        inst_qps = 1.0 / dt

        # 1분 EWMA (반감기 60초)
        alpha = 1 - math.exp(-dt / 60.0)
        self._qps_ewma_1m = (1 - alpha) * self._qps_ewma_1m + alpha * inst_qps
        self._hit_rate_ewma_1m = (
            (1 - alpha) * self._hit_rate_ewma_1m + alpha * hit_increment
        )

        self._last_tick = now

    def record_code_query(
        self, has_exact_match: bool, stage0_count: int, stage1_count: int,
    ) -> None:
        """코드 쿼리 기록

        Args:
            has_exact_match: ExactMatch 히트 여부
            stage0_count: Stage 0 후보 수
            stage1_count: Stage 1 후보 수
        """
        with self._lock:
            self.code_queries_total += 1
            hit_inc = 1 if has_exact_match else 0
            if has_exact_match:
                self.exact_match_hits_total += 1
            self.stage0_candidates_last = stage0_count
            self.stage1_candidates_last = stage1_count
            self._tick_rate(hit_inc)

    def record_rrf_fusion(self) -> None:
        """RRF 융합 사용 기록"""
        with self._lock:
            self.rrf_fusion_used_total += 1

    def record_citation_forced(self) -> None:
        """Citation 강제 기록"""
        with self._lock:
            self.citation_forced_total += 1

    def record_latency(self, latency_ms: float) -> None:
        """검색 지연시간 기록

        Args:
            latency_ms: 지연시간 (밀리초)
        """
        with self._lock:
            self.latency_samples.append(latency_ms)

    @contextmanager
    def measure_retrieval_latency(self) -> Iterator[None]:
        """검색 지연시간 측정 컨텍스트 매니저

        Example:
            with metrics.measure_retrieval_latency():
                results = retriever.search(query, top_k=10)
        """
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            dt_ms = (time.perf_counter_ns() - t0) / 1_000_000
            self.record_latency(dt_ms)

    def get_metrics(self) -> dict:
        """메트릭 스냅샷 반환 (락 홀드 최소화)

        Returns:
            dict: {
                code_queries_total, exact_match_hits_total, exact_match_hit_rate,
                stage0_candidates_last, stage1_candidates_last,
                rrf_fusion_used_total, citation_forced_total,
                retrieval_latency_ms_p50, retrieval_latency_ms_p95,
                qps_ewma_1m, hit_rate_ewma_1m
            }
        """
        # 락 내부: 스냅샷만 확보하고 즉시 해제
        with self._lock:
            total = self.code_queries_total
            hits = self.exact_match_hits_total
            stage0 = self.stage0_candidates_last
            stage1 = self.stage1_candidates_last
            rrf = self.rrf_fusion_used_total
            cit = self.citation_forced_total
            samples = list(self.latency_samples)
            qps_ewma = self._qps_ewma_1m
            hit_ewma = self._hit_rate_ewma_1m

        # 락 밖: 계산 (정렬/백분위)
        hit_rate = (hits / total) if total > 0 else 0.0

        if samples:
            samples.sort()
            p50 = int(_percentile(samples, 0.50))
            p95 = int(_percentile(samples, 0.95))
        else:
            p50 = p95 = 0

        return {
            "code_queries_total": total,
            "exact_match_hits_total": hits,
            "exact_match_hit_rate": round(hit_rate, 3),
            "stage0_candidates_last": stage0,
            "stage1_candidates_last": stage1,
            "rrf_fusion_used_total": rrf,
            "citation_forced_total": cit,
            "retrieval_latency_ms_p50": p50,
            "retrieval_latency_ms_p95": p95,
            "qps_ewma_1m": round(qps_ewma, 2),
            "hit_rate_ewma_1m": round(hit_ewma, 3),
        }

    def to_prometheus_text(self) -> str:
        """프로메테우스 텍스트 포맷으로 메트릭 내보내기

        Returns:
            str: 프로메테우스 메트릭 텍스트
        """
        m = self.get_metrics()
        lines = [
            "# HELP code_queries_total Total number of code queries",
            "# TYPE code_queries_total counter",
            f'code_queries_total {m["code_queries_total"]}',
            "",
            "# HELP exact_match_hits_total Total number of exact match hits",
            "# TYPE exact_match_hits_total counter",
            f'exact_match_hits_total {m["exact_match_hits_total"]}',
            "",
            "# HELP exact_match_hit_rate Exact match hit rate",
            "# TYPE exact_match_hit_rate gauge",
            f'exact_match_hit_rate {m["exact_match_hit_rate"]}',
            "",
            "# HELP stage0_candidates_last Last stage 0 candidates count",
            "# TYPE stage0_candidates_last gauge",
            f'stage0_candidates_last {m["stage0_candidates_last"]}',
            "",
            "# HELP stage1_candidates_last Last stage 1 candidates count",
            "# TYPE stage1_candidates_last gauge",
            f'stage1_candidates_last {m["stage1_candidates_last"]}',
            "",
            "# HELP rrf_fusion_used_total Total RRF fusion uses",
            "# TYPE rrf_fusion_used_total counter",
            f'rrf_fusion_used_total {m["rrf_fusion_used_total"]}',
            "",
            "# HELP citation_forced_total Total citation forced count",
            "# TYPE citation_forced_total counter",
            f'citation_forced_total {m["citation_forced_total"]}',
            "",
            "# HELP retrieval_latency_ms_p50 Retrieval latency p50 (ms)",
            "# TYPE retrieval_latency_ms_p50 gauge",
            f'retrieval_latency_ms_p50 {m["retrieval_latency_ms_p50"]}',
            "",
            "# HELP retrieval_latency_ms_p95 Retrieval latency p95 (ms)",
            "# TYPE retrieval_latency_ms_p95 gauge",
            f'retrieval_latency_ms_p95 {m["retrieval_latency_ms_p95"]}',
            "",
            "# HELP qps_ewma_1m Queries per second (1m EWMA)",
            "# TYPE qps_ewma_1m gauge",
            f'qps_ewma_1m {m["qps_ewma_1m"]}',
            "",
            "# HELP hit_rate_ewma_1m Hit rate (1m EWMA)",
            "# TYPE hit_rate_ewma_1m gauge",
            f'hit_rate_ewma_1m {m["hit_rate_ewma_1m"]}',
        ]
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """메트릭 초기화 (테스트용)"""
        with self._lock:
            self.code_queries_total = 0
            self.exact_match_hits_total = 0
            self.rrf_fusion_used_total = 0
            self.citation_forced_total = 0
            self.stage0_candidates_last = 0
            self.stage1_candidates_last = 0
            self.latency_samples.clear()
            self._last_tick = time.perf_counter()
            self._qps_ewma_1m = 0.0
            self._hit_rate_ewma_1m = 0.0
            logger.info("📊 메트릭 초기화됨")


# 전역 싱글턴 인스턴스
_metrics_instance = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> CodeSearchMetrics:
    """전역 메트릭 수집기 인스턴스 반환 (싱글턴)

    Returns:
        CodeSearchMetrics: 전역 메트릭 수집기
    """
    global _metrics_instance
    if _metrics_instance is None:
        with _metrics_lock:
            if _metrics_instance is None:
                _metrics_instance = CodeSearchMetrics(latency_window_size=2000)
                logger.info("📊 CodeSearchMetrics v2.0 초기화됨 (싱글턴)")
    return _metrics_instance
