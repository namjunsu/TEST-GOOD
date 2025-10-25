"""RAG 성능 지표 수집

메트릭:
- Hit@k: 상위 k개 내 정답 포함 비율
- MRR: Mean Reciprocal Rank
- Latency: P50, P95, P99
- Failure rate: 에러 발생 비율

Example:
    >>> tracker = MetricsTracker()
    >>> tracker.record_query(query="...", latency=1.2, success=True, hit_rank=2)
    >>> summary = tracker.get_summary()
    >>> print(f"Hit@5: {summary['hit_at_5']:.2%}")
"""

from dataclasses import dataclass
from typing import List, Optional
import statistics

from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# 데이터 클래스
# ============================================================================

@dataclass
class QueryMetrics:
    """단일 쿼리 지표

    Attributes:
        query: 질문 (해시 또는 전문)
        latency: 실행 시간 (초)
        success: 성공 여부
        hit_rank: 정답 문서 순위 (1-based, 없으면 None)
        retrieved_count: 검색된 문서 개수
        error: 에러 메시지 (실패 시)
    """
    query: str
    latency: float
    success: bool
    hit_rank: Optional[int] = None
    retrieved_count: int = 0
    error: Optional[str] = None


@dataclass
class MetricsSummary:
    """집계 지표

    Attributes:
        total_queries: 전체 쿼리 수
        success_rate: 성공 비율
        hit_at_1: Hit@1
        hit_at_3: Hit@3
        hit_at_5: Hit@5
        mrr: Mean Reciprocal Rank
        p50_latency: 50th percentile 레이턴시
        p95_latency: 95th percentile 레이턴시
        p99_latency: 99th percentile 레이턴시
        avg_latency: 평균 레이턴시
    """
    total_queries: int
    success_rate: float
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float
    p50_latency: float
    p95_latency: float
    p99_latency: float
    avg_latency: float


# ============================================================================
# 메트릭 트래커
# ============================================================================

class MetricsTracker:
    """RAG 성능 지표 추적기

    Example:
        >>> tracker = MetricsTracker()
        >>> tracker.record_query("질문1", latency=1.2, success=True, hit_rank=2)
        >>> tracker.record_query("질문2", latency=0.8, success=True, hit_rank=1)
        >>> summary = tracker.get_summary()
        >>> print(f"Hit@1: {summary.hit_at_1:.2%}, MRR: {summary.mrr:.3f}")
    """

    def __init__(self):
        """트래커 초기화"""
        self.metrics: List[QueryMetrics] = []
        logger.info("MetricsTracker initialized")

    def record_query(
        self,
        query: str,
        latency: float,
        success: bool,
        hit_rank: Optional[int] = None,
        retrieved_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """쿼리 지표 기록

        Args:
            query: 질문 텍스트
            latency: 실행 시간 (초)
            success: 성공 여부
            hit_rank: 정답 순위 (1-based, 없으면 None)
            retrieved_count: 검색된 문서 수
            error: 에러 메시지
        """
        metric = QueryMetrics(
            query=query[:100],  # 100자만 저장
            latency=latency,
            success=success,
            hit_rank=hit_rank,
            retrieved_count=retrieved_count,
            error=error,
        )
        self.metrics.append(metric)

        logger.debug(
            f"Recorded metric: success={success}, latency={latency:.2f}s, "
            f"hit_rank={hit_rank}, retrieved={retrieved_count}"
        )

    def get_summary(self) -> MetricsSummary:
        """집계 지표 계산

        Returns:
            MetricsSummary: 전체 성능 지표
        """
        if not self.metrics:
            return MetricsSummary(
                total_queries=0,
                success_rate=0.0,
                hit_at_1=0.0,
                hit_at_3=0.0,
                hit_at_5=0.0,
                mrr=0.0,
                p50_latency=0.0,
                p95_latency=0.0,
                p99_latency=0.0,
                avg_latency=0.0,
            )

        total = len(self.metrics)
        successes = [m for m in self.metrics if m.success]
        latencies = [m.latency for m in self.metrics]

        # 성공률
        success_rate = len(successes) / total

        # Hit@k 계산
        hit_at_1 = sum(1 for m in successes if m.hit_rank == 1) / total
        hit_at_3 = sum(1 for m in successes if m.hit_rank and m.hit_rank <= 3) / total
        hit_at_5 = sum(1 for m in successes if m.hit_rank and m.hit_rank <= 5) / total

        # MRR 계산
        reciprocal_ranks = [
            1.0 / m.hit_rank for m in successes if m.hit_rank is not None
        ]
        mrr = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0

        # Latency percentiles
        p50 = statistics.median(latencies)
        p95 = self._percentile(latencies, 0.95)
        p99 = self._percentile(latencies, 0.99)
        avg = statistics.mean(latencies)

        summary = MetricsSummary(
            total_queries=total,
            success_rate=success_rate,
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            hit_at_5=hit_at_5,
            mrr=mrr,
            p50_latency=p50,
            p95_latency=p95,
            p99_latency=p99,
            avg_latency=avg,
        )

        logger.info(
            f"Metrics summary: {total} queries, "
            f"success_rate={success_rate:.2%}, "
            f"hit@5={hit_at_5:.2%}, "
            f"MRR={mrr:.3f}, "
            f"P50={p50:.2f}s"
        )

        return summary

    def reset(self) -> None:
        """지표 초기화"""
        self.metrics.clear()
        logger.info("Metrics reset")

    def _percentile(self, values: List[float], p: float) -> float:
        """백분위수 계산

        Args:
            values: 값 목록
            p: 백분위 (0.0~1.0)

        Returns:
            p번째 백분위수
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * p)
        return sorted_values[min(index, len(sorted_values) - 1)]


# ============================================================================
# 전역 싱글톤 (옵션)
# ============================================================================

_global_tracker: Optional[MetricsTracker] = None


def get_metrics_tracker() -> MetricsTracker:
    """전역 메트릭 트래커 반환 (싱글톤)

    Returns:
        MetricsTracker: 전역 트래커
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = MetricsTracker()
    return _global_tracker
