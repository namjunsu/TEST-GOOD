"""SmartTokenAllocator - 동적 토큰 할당 시스템

2026-01-10: P2 중기 최적화
- 컨텍스트 길이, 쿼리 복잡도 기반 동적 토큰 할당
- 성능 피드백 루프 (시간/품질 기록)
- 반복적인 정적 설정 조정 문제 해결
"""

import time
from typing import Optional

from app.core.logging import get_logger
from config.constants import TokenConfig

logger = get_logger(__name__)


class SmartTokenAllocator:
    """응답 복잡도 기반 동적 토큰 할당

    기능:
    - 컨텍스트 길이 기반 조정
    - 쿼리 복잡도 기반 조정
    - 성능 피드백 루프 (선택적)
    """

    def __init__(self, enable_feedback: bool = False):
        """초기화

        Args:
            enable_feedback: 성능 피드백 루프 활성화 여부
        """
        self.enable_feedback = enable_feedback
        self.history: list[dict] = []  # 성능 기록

    def allocate(
        self,
        mode: str,
        context_len: int = 0,
        query_complexity: float = 0.5,
    ) -> int:
        """동적 토큰 할당

        Args:
            mode: 모드 (rag, qa, detailed 등)
            context_len: 컨텍스트 길이 (문자 수)
            query_complexity: 쿼리 복잡도 (0.0~1.0)
                - 0.0: 매우 간단 (단일 단어 질문)
                - 0.5: 보통 (일반적인 질문)
                - 1.0: 매우 복잡 (다중 조건, 비교 등)

        Returns:
            할당된 토큰 수
        """
        # 기본 토큰 (TokenConfig에서 가져옴)
        base_tokens = TokenConfig.get(mode)

        # 컨텍스트 길이 기반 조정
        # 6000자 기준으로 정규화 (일반적인 문서 크기)
        context_factor = min(context_len / 6000, 1.5) if context_len > 0 else 1.0

        # 쿼리 복잡도 기반 조정
        # 복잡도 0.0~1.0을 0.8~1.2 배수로 매핑
        complexity_factor = 0.8 + (query_complexity * 0.4)

        # 최종 할당
        allocated = int(base_tokens * context_factor * complexity_factor)

        # 범위 제한 (기본값의 50%~200%)
        min_tokens = int(base_tokens * 0.5)
        max_tokens = int(base_tokens * 2.0)
        allocated = max(min_tokens, min(allocated, max_tokens))

        logger.debug(
            f"동적 토큰 할당: mode={mode} base={base_tokens} "
            f"context_factor={context_factor:.2f} complexity_factor={complexity_factor:.2f} "
            f"→ allocated={allocated}"
        )

        return allocated

    def estimate_complexity(self, query: str) -> float:
        """쿼리 복잡도 추정

        Args:
            query: 사용자 질문

        Returns:
            복잡도 점수 (0.0~1.0)
        """
        if not query:
            return 0.5

        complexity = 0.5  # 기본값

        # 길이 기반 (긴 질문 = 더 복잡)
        if len(query) > 100:
            complexity += 0.1
        if len(query) > 200:
            complexity += 0.1

        # 키워드 기반
        complex_keywords = [
            "비교", "차이", "어떤 것", "모두", "전체", "목록",
            "왜", "이유", "어떻게", "방법",
            "그리고", "또는", "그러나", "하지만"
        ]
        for keyword in complex_keywords:
            if keyword in query:
                complexity += 0.05

        # 질문 부호 개수 (다중 질문)
        question_count = query.count("?")
        if question_count > 1:
            complexity += 0.1 * (question_count - 1)

        # 0.0~1.0 범위로 제한
        return min(max(complexity, 0.0), 1.0)

    def record_performance(
        self,
        mode: str,
        tokens: int,
        generation_time: float,
        quality_score: Optional[float] = None,
    ) -> None:
        """성능 기록 (피드백 루프)

        Args:
            mode: 모드
            tokens: 사용된 토큰 수
            generation_time: 생성 시간 (초)
            quality_score: 품질 점수 (0.0~1.0, 선택적)
        """
        if not self.enable_feedback:
            return

        self.history.append({
            "mode": mode,
            "tokens": tokens,
            "time": generation_time,
            "quality": quality_score,
            "timestamp": time.time()
        })

        # 최근 100개만 유지 (메모리 관리)
        if len(self.history) > 100:
            self.history = self.history[-100:]

        logger.debug(
            f"성능 기록: mode={mode} tokens={tokens} "
            f"time={generation_time:.2f}s quality={quality_score}"
        )

    def get_average_performance(self, mode: str) -> dict:
        """모드별 평균 성능 조회

        Args:
            mode: 모드

        Returns:
            평균 성능 지표 (tokens, time, quality)
        """
        if not self.history:
            return {"tokens": 0, "time": 0.0, "quality": None, "count": 0}

        mode_history = [h for h in self.history if h["mode"] == mode]
        if not mode_history:
            return {"tokens": 0, "time": 0.0, "quality": None, "count": 0}

        avg_tokens = sum(h["tokens"] for h in mode_history) / len(mode_history)
        avg_time = sum(h["time"] for h in mode_history) / len(mode_history)

        quality_scores = [h["quality"] for h in mode_history if h["quality"] is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

        return {
            "tokens": int(avg_tokens),
            "time": avg_time,
            "quality": avg_quality,
            "count": len(mode_history)
        }


# 전역 인스턴스 (싱글톤)
_allocator: Optional[SmartTokenAllocator] = None


def get_token_allocator(enable_feedback: bool = False) -> SmartTokenAllocator:
    """토큰 할당기 싱글톤 인스턴스 반환

    Args:
        enable_feedback: 성능 피드백 루프 활성화 (최초 생성 시만 적용)

    Returns:
        SmartTokenAllocator 인스턴스
    """
    global _allocator
    if _allocator is None:
        _allocator = SmartTokenAllocator(enable_feedback=enable_feedback)
    return _allocator


__all__ = ["SmartTokenAllocator", "get_token_allocator"]
