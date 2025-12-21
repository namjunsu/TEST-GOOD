"""RAG 모드 결정 로직 (ModeResolver)

pipeline.py에서 분리된 모드 결정 로직.
검색 결과와 쿼리 특성을 기반으로 chat/rag 모드를 결정합니다.
"""

import threading
from dataclasses import dataclass, field
from typing import Any

from app.config.settings import settings
from app.core.logging import get_logger
from app.rag.query_routing import (
    force_chat_mode,
    get_keyword_coverage,
    has_domain_keyword,
)
from app.rag.utils.text import get_query_token_count
from config.constants import PipelineConfig

logger = get_logger(__name__)


@dataclass
class ModeDecision:
    """모드 결정 결과

    Attributes:
        mode: 결정된 모드 ("chat" 또는 "rag")
        top_score: 최고 검색 점수
        reason: 결정 이유
        metrics: 추가 메트릭
    """

    mode: str
    top_score: float
    reason: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


class ModeResolver:
    """RAG 모드 결정기

    검색 결과와 쿼리 특성을 분석하여
    chat/rag 모드를 결정합니다.
    """

    def __init__(self, config: type = PipelineConfig):
        """초기화

        Args:
            config: 파이프라인 설정 클래스
        """
        self.config = config

    def resolve(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> ModeDecision:
        """모드 결정

        Args:
            query: 사용자 질문
            results: 검색 결과 리스트

        Returns:
            ModeDecision 객체
        """
        mode_env = settings.MODE
        top_score = results[0].get("score", 0.0) if results else 0.0
        metrics = {"top_score": top_score}

        if mode_env == "AUTO":
            return self._resolve_auto_mode(query, results, top_score, metrics)
        elif mode_env == "CHAT":
            metrics["top_score"] = 0.0  # CHAT 모드에서는 점수 무시
            return ModeDecision(
                mode="chat",
                top_score=0.0,
                reason="MODE=CHAT",
                metrics=metrics,
            )
        else:  # RAG, SUMMARIZE
            return ModeDecision(
                mode="rag",
                top_score=top_score,
                reason=f"MODE={mode_env}",
                metrics=metrics,
            )

    def _resolve_auto_mode(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_score: float,
        metrics: dict[str, Any],
    ) -> ModeDecision:
        """AUTO 모드에서 chat/rag 결정

        Args:
            query: 사용자 질문
            results: 검색 결과
            top_score: 최고 점수
            metrics: 메트릭 딕셔너리

        Returns:
            ModeDecision 객체
        """
        # 1. 강제 CHAT 모드 체크 (스몰토크/산술/짧은 질의)
        should_force, force_reason = force_chat_mode(query)
        if should_force:
            metrics["force_chat_reason"] = force_reason
            logger.info(f"🎯 AUTO 모드: CHAT 강제 적용 (이유: {force_reason})")
            return ModeDecision(
                mode="chat",
                top_score=top_score,
                reason=f"force_chat:{force_reason}",
                metrics=metrics,
            )

        # 2. 도메인 키워드 + 절대값 임계값 기반 판단
        has_keyword = has_domain_keyword(query)
        token_count = get_query_token_count(query)
        use_absolute = settings.RAG_MIN_SCORE_POLICY == "absolute"

        if use_absolute:
            return self._resolve_absolute_policy(
                query, results, top_score, has_keyword, token_count, metrics
            )
        else:
            return self._resolve_normalized_policy(query, top_score, metrics)

    def _resolve_absolute_policy(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_score: float,
        has_keyword: bool,
        token_count: int,
        metrics: dict[str, Any],
    ) -> ModeDecision:
        """절대값 정책으로 모드 결정"""
        vec_min = settings.VEC_MIN_ABS

        pass_abs_threshold = top_score >= vec_min
        pass_domain = has_keyword
        pass_length = token_count >= self.config.MIN_TOKEN_COUNT_FOR_RAG

        # Coverage Gate
        keyword_coverage = get_keyword_coverage(query, results)
        min_coverage = settings.MIN_KEYWORD_COVERAGE
        pass_coverage = keyword_coverage >= min_coverage

        should_use_rag = (
            pass_abs_threshold and pass_domain and pass_length and pass_coverage
        )
        mode = "rag" if should_use_rag else "chat"

        metrics["keyword_coverage"] = keyword_coverage
        metrics["pass_abs_threshold"] = pass_abs_threshold
        metrics["pass_domain"] = pass_domain
        metrics["pass_length"] = pass_length
        metrics["pass_coverage"] = pass_coverage

        logger.info(
            f"🎯 AUTO 모드 (절대값): top_score={top_score:.3f}, "
            f"has_keyword={has_keyword}, token_count={token_count}, "
            f"coverage={keyword_coverage}/{min_coverage}, "
            f"threshold={vec_min}, selected_mode={mode}",
        )

        return ModeDecision(
            mode=mode,
            top_score=top_score,
            reason="absolute_policy",
            metrics=metrics,
        )

    def _resolve_normalized_policy(
        self,
        query: str,  # noqa: ARG002 - 향후 쿼리 기반 로직 확장용
        top_score: float,
        metrics: dict[str, Any],
    ) -> ModeDecision:
        """정규화 정책으로 모드 결정 (레거시)"""
        rag_min_score = settings.RAG_MIN_SCORE
        mode = "rag" if top_score >= rag_min_score else "chat"

        logger.info(
            f"🎯 AUTO 모드 (정규화): top_score={top_score:.3f}, "
            f"threshold={rag_min_score}, selected_mode={mode}",
        )

        return ModeDecision(
            mode=mode,
            top_score=top_score,
            reason="normalized_policy",
            metrics=metrics,
        )


# 싱글톤 인스턴스 (스레드 안전)
_resolver_instance: ModeResolver | None = None
_resolver_lock = threading.Lock()


def get_mode_resolver() -> ModeResolver:
    """ModeResolver 싱글톤 인스턴스 반환 (스레드 안전)"""
    global _resolver_instance
    if _resolver_instance is None:
        with _resolver_lock:
            # Double-check locking
            if _resolver_instance is None:
                _resolver_instance = ModeResolver()
    return _resolver_instance
