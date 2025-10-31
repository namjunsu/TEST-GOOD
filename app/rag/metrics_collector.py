"""RAG 코드 검색 메트릭 수집기 (Thread-safe)

전역 싱글턴으로 동작하며, HybridRetriever/ExactMatchRetriever에서 호출
"""

import threading
import time
from typing import List
from collections import deque
from app.core.logging import get_logger

logger = get_logger(__name__)


class CodeSearchMetrics:
    """코드 검색 메트릭 수집기 (Thread-safe)"""

    def __init__(self):
        self._lock = threading.Lock()

        # 카운터
        self.code_queries_total = 0
        self.exact_match_hits_total = 0
        self.rrf_fusion_used_total = 0
        self.citation_forced_total = 0  # Patch C: Citation 강제 카운터

        # 마지막 검색 상태
        self.stage0_candidates_last = 0
        self.stage1_candidates_last = 0

        # 지연시간 히스토그램 (최근 1000개)
        self.latency_samples = deque(maxlen=1000)

    def record_code_query(self, has_exact_match: bool, stage0_count: int, stage1_count: int):
        """코드 쿼리 기록

        Args:
            has_exact_match: ExactMatch 히트 여부
            stage0_count: Stage 0 후보 수
            stage1_count: Stage 1 후보 수
        """
        with self._lock:
            self.code_queries_total += 1
            if has_exact_match:
                self.exact_match_hits_total += 1
            self.stage0_candidates_last = stage0_count
            self.stage1_candidates_last = stage1_count

    def record_rrf_fusion(self):
        """RRF 융합 사용 기록"""
        with self._lock:
            self.rrf_fusion_used_total += 1

    def record_citation_forced(self):
        """Citation 강제 기록 (Patch C)"""
        with self._lock:
            self.citation_forced_total += 1

    def record_latency(self, latency_ms: float):
        """검색 지연시간 기록

        Args:
            latency_ms: 지연시간 (밀리초)
        """
        with self._lock:
            self.latency_samples.append(latency_ms)

    def get_metrics(self) -> dict:
        """메트릭 스냅샷 반환

        Returns:
            dict: {
                code_queries_total, exact_match_hits_total, exact_match_hit_rate,
                stage0_candidates_last, stage1_candidates_last,
                rrf_fusion_used_total,
                retrieval_latency_ms_p50, retrieval_latency_ms_p95
            }
        """
        with self._lock:
            # Hit rate 계산
            hit_rate = 0.0
            if self.code_queries_total > 0:
                hit_rate = self.exact_match_hits_total / self.code_queries_total

            # 지연시간 백분위수 계산
            p50 = 0
            p95 = 0
            if self.latency_samples:
                sorted_samples = sorted(self.latency_samples)
                n = len(sorted_samples)
                p50_idx = int(n * 0.50)
                p95_idx = int(n * 0.95)
                p50 = int(sorted_samples[p50_idx])
                p95 = int(sorted_samples[p95_idx])

            return {
                "code_queries_total": self.code_queries_total,
                "exact_match_hits_total": self.exact_match_hits_total,
                "exact_match_hit_rate": round(hit_rate, 3),
                "stage0_candidates_last": self.stage0_candidates_last,
                "stage1_candidates_last": self.stage1_candidates_last,
                "rrf_fusion_used_total": self.rrf_fusion_used_total,
                "citation_forced_total": self.citation_forced_total,  # Patch C
                "retrieval_latency_ms_p50": p50,
                "retrieval_latency_ms_p95": p95,
            }

    def reset(self):
        """메트릭 초기화 (테스트용)"""
        with self._lock:
            self.code_queries_total = 0
            self.exact_match_hits_total = 0
            self.rrf_fusion_used_total = 0
            self.citation_forced_total = 0
            self.stage0_candidates_last = 0
            self.stage1_candidates_last = 0
            self.latency_samples.clear()
            logger.info("📊 메트릭 초기화됨")


# 전역 싱글턴 인스턴스
_metrics_instance = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> CodeSearchMetrics:
    """전역 메트릭 수집기 인스턴스 반환 (싱글턴)"""
    global _metrics_instance
    if _metrics_instance is None:
        with _metrics_lock:
            if _metrics_instance is None:
                _metrics_instance = CodeSearchMetrics()
                logger.info("📊 CodeSearchMetrics 초기화됨 (싱글턴)")
    return _metrics_instance
