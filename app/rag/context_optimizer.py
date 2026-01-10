"""ContextOptimizer - 적응형 컨텍스트 윈도우

2026-01-10: P2 중기 최적화
- 쿼리 복잡도, 응답 속도 기반 동적 컨텍스트 길이 조정
- 하드코딩된 컨텍스트 길이 문제 해결
"""

from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class ContextOptimizer:
    """동적 컨텍스트 윈도우 최적화

    기능:
    - detail_level 기반 기본 길이
    - 쿼리 복잡도 기반 조정
    - 응답 속도 피드백 (선택적)
    """

    # 기본 컨텍스트 길이 (문자 수)
    BASE_LENGTHS = {
        "brief": 5000,
        "normal": 10000,
        "detailed": 16000,
    }

    # 최대 컨텍스트 길이
    MAX_CONTEXT = 20000

    def __init__(self):
        """초기화"""
        self.avg_response_times: dict[str, float] = {}  # 모드별 평균 응답 시간

    def optimize_length(
        self,
        detail_level: str = "normal",
        query_complexity: float = 0.5,
        mode: Optional[str] = None,
    ) -> int:
        """적응형 컨텍스트 길이 계산

        Args:
            detail_level: 상세도 ("brief", "normal", "detailed")
            query_complexity: 쿼리 복잡도 (0.0~1.0)
            mode: 모드 (응답 시간 피드백용, 선택적)

        Returns:
            최적화된 컨텍스트 길이 (문자 수)
        """
        # 기본 길이
        base_len = self.BASE_LENGTHS.get(detail_level, self.BASE_LENGTHS["normal"])

        # 쿼리 복잡도 조정 (복잡한 쿼리 = 더 많은 컨텍스트)
        # complexity 0.0~1.0을 0.8~1.2 배수로 매핑
        complexity_factor = 0.8 + (query_complexity * 0.4)
        adjusted = base_len * complexity_factor

        # 응답 속도 피드백 (느리면 컨텍스트 감소)
        if mode and mode in self.avg_response_times:
            avg_time = self.avg_response_times[mode]
            if avg_time > 3.0:  # 3초 초과
                speed_factor = 0.8
                adjusted *= speed_factor
                logger.debug(
                    f"응답 속도 느림 감지 (avg={avg_time:.2f}s) → "
                    f"컨텍스트 20% 감소"
                )
            elif avg_time < 1.0:  # 1초 미만 (여유 있음)
                speed_factor = 1.1
                adjusted = min(adjusted * speed_factor, self.MAX_CONTEXT)
                logger.debug(
                    f"응답 속도 빠름 (avg={avg_time:.2f}s) → "
                    f"컨텍스트 10% 증가 (최대값 제한)"
                )

        # 최대값 제한
        final_len = int(min(adjusted, self.MAX_CONTEXT))

        logger.debug(
            f"컨텍스트 최적화: detail={detail_level} complexity={query_complexity:.2f} "
            f"base={base_len} → {final_len}"
        )

        return final_len

    def record_response_time(self, mode: str, response_time: float) -> None:
        """응답 시간 기록 (피드백용)

        Args:
            mode: 모드
            response_time: 응답 시간 (초)
        """
        # 지수 이동 평균 (EMA) 사용
        alpha = 0.3  # 가중치
        if mode in self.avg_response_times:
            self.avg_response_times[mode] = (
                alpha * response_time + (1 - alpha) * self.avg_response_times[mode]
            )
        else:
            self.avg_response_times[mode] = response_time

        logger.debug(f"응답 시간 기록: mode={mode} time={response_time:.2f}s avg={self.avg_response_times[mode]:.2f}s")

    def get_average_response_time(self, mode: str) -> Optional[float]:
        """모드별 평균 응답 시간 조회

        Args:
            mode: 모드

        Returns:
            평균 응답 시간 (초) 또는 None
        """
        return self.avg_response_times.get(mode)


# 전역 인스턴스 (싱글톤)
_optimizer: Optional[ContextOptimizer] = None


def get_context_optimizer() -> ContextOptimizer:
    """컨텍스트 최적화기 싱글톤 인스턴스 반환

    Returns:
        ContextOptimizer 인스턴스
    """
    global _optimizer
    if _optimizer is None:
        _optimizer = ContextOptimizer()
    return _optimizer


__all__ = ["ContextOptimizer", "get_context_optimizer"]
