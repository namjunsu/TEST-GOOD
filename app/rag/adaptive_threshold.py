"""AdaptiveScoreThreshold - 쿼리 타입별 동적 임계값

2026-01-10: P3 장기 리팩토링
- 쿼리 타입, 길이 기반 동적 점수 임계값
- 정적 임계값 (0.35) 문제 해결
"""

from typing import Optional

from app.core.logging import get_logger
from config.constants import SearchConfig

logger = get_logger(__name__)


class AdaptiveScoreThreshold:
    """쿼리 타입별 동적 검색 점수 임계값

    기능:
    - 쿼리 타입 감지 (목록, 구체적 사실, 비교 등)
    - 쿼리 길이 기반 조정
    - 기본 임계값 (SearchConfig) 기반
    """

    def __init__(self):
        """초기화"""
        self.base_threshold = SearchConfig.RAG_MIN_SCORE

    def get_threshold(
        self,
        query: str,
        query_type: Optional[str] = None,
    ) -> float:
        """동적 임계값 계산

        Args:
            query: 사용자 질문
            query_type: 쿼리 타입 (선택적, 없으면 자동 감지)

        Returns:
            적응형 임계값 (0.0~1.0)
        """
        if not query:
            return self.base_threshold

        # 쿼리 타입 자동 감지
        if query_type is None:
            query_type = self._detect_query_type(query)

        # 기본 임계값
        threshold = self.base_threshold

        # 쿼리 타입별 조정
        if query_type == "list":
            # 목록 질의: 낮은 임계값 (많은 결과 필요)
            threshold *= 0.7  # 35% → 24.5%
            logger.debug(f"목록 쿼리 감지 → 임계값 30% 감소")

        elif query_type == "specific_fact":
            # 구체적 사실: 높은 임계값 (정확성 우선)
            threshold *= 1.4  # 35% → 49%
            logger.debug(f"구체적 사실 쿼리 감지 → 임계값 40% 증가")

        elif query_type == "comparison":
            # 비교: 중간 임계값
            threshold *= 1.1  # 35% → 38.5%
            logger.debug(f"비교 쿼리 감지 → 임계값 10% 증가")

        # 쿼리 길이 기반 추가 조정
        # 긴 쿼리 = 더 구체적 = 높은 임계값
        query_len = len(query)
        if query_len > 100:
            length_factor = min(query_len / 100, 1.2)  # 최대 20% 증가
            threshold *= length_factor
            logger.debug(f"긴 쿼리 ({query_len}자) → 임계값 {(length_factor-1)*100:.0f}% 증가")

        # 범위 제한 (0.2 ~ 0.6)
        threshold = max(0.2, min(threshold, 0.6))

        logger.debug(
            f"적응형 임계값: type={query_type} len={len(query)} "
            f"base={self.base_threshold:.2f} → {threshold:.2f}"
        )

        return threshold

    def _detect_query_type(self, query: str) -> str:
        """쿼리 타입 자동 감지

        Args:
            query: 사용자 질문

        Returns:
            쿼리 타입 ("list", "specific_fact", "comparison", "general")
        """
        query_lower = query.lower()

        # 목록 질의 패턴
        list_keywords = [
            "뭐가 있", "어떤 것들", "목록", "리스트", "전체", "모두",
            "어떤게", "몇 개", "몇개", "어떤 거"
        ]
        if any(kw in query_lower for kw in list_keywords):
            return "list"

        # 비교 질의 패턴
        comparison_keywords = [
            "비교", "차이", "대안", "옵션", "vs", "어느", "어떤 것이",
            "더 좋", "더 나은"
        ]
        if any(kw in query_lower for kw in comparison_keywords):
            return "comparison"

        # 구체적 사실 질의 패턴
        fact_keywords = [
            "얼마", "언제", "누구", "어디", "몇", "무엇",
            "금액", "비용", "가격", "날짜", "시간"
        ]
        # 특정 수치/날짜 포함 여부 확인
        has_specific_info = any(kw in query_lower for kw in fact_keywords)

        # 파일명 또는 날짜 패턴 포함
        import re
        has_filename = bool(re.search(r'\d{4}[-_]\d{2}[-_]\d{2}', query))

        if has_specific_info or has_filename:
            return "specific_fact"

        # 기본: 일반 질의
        return "general"


# 전역 인스턴스 (싱글톤)
_threshold_adapter: Optional[AdaptiveScoreThreshold] = None


def get_adaptive_threshold() -> AdaptiveScoreThreshold:
    """적응형 임계값 어댑터 싱글톤 인스턴스 반환

    Returns:
        AdaptiveScoreThreshold 인스턴스
    """
    global _threshold_adapter
    if _threshold_adapter is None:
        _threshold_adapter = AdaptiveScoreThreshold()
    return _threshold_adapter


__all__ = ["AdaptiveScoreThreshold", "get_adaptive_threshold"]
