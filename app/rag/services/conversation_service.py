"""ConversationService - 대화 로깅 서비스

Phase 3 리팩토링: pipeline.py의 대화 로깅 로직을 별도 서비스로 추출

책임:
- 응답 결과 분석
- 성공/실패 판정
- 대화 로그 DB 저장
"""

import os
import time
from typing import Any, Optional

from app.core.logging import get_logger
from app.rag.conversation_logger import get_conversation_logger
from config.constants import PipelineConfig

logger = get_logger(__name__)


class ConversationService:
    """대화 로깅 서비스

    응답 결과를 분석하여 대화 로그 DB에 저장.

    책임:
    - 검색 결과 수집 (evidence, citations)
    - 성공/실패 판정 (timeout, no_answer, hallucination 감지)
    - 메트릭 수집 (latency, search_count, top_score)
    - ConversationLogger에 위임
    """

    def __init__(self) -> None:
        """초기화"""
        self._conv_logger = get_conversation_logger()

    def log_answer(
        self,
        result: dict[str, Any],
        mode: str,
        query: str,
        start_time: float,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """응답 결과 로깅

        Args:
            result: 응답 딕셔너리
            mode: 처리 모드
            query: 원본 쿼리
            start_time: 시작 시간 (time.time())
            client_ip: 클라이언트 IP
            session_id: 세션 ID
            **kwargs: 추가 메타데이터
        """
        try:
            elapsed_ms = int((time.time() - start_time) * 1000)

            # 검색 결과 수집
            evidence = result.get("evidence") or result.get("citations") or []
            search_count = len(evidence)
            top_score = evidence[0].get("score", 0.0) if evidence else 0.0

            # 성공/실패 판정
            success, error_type = self._evaluate_result(result, mode, elapsed_ms, search_count)

            # 로깅 실행
            self._conv_logger.log(
                query=query,
                answer=result.get("text", ""),
                mode=mode,
                sources=evidence,
                confidence=0.0,
                latency_ms=elapsed_ms,
                client_ip=client_ip,
                session_id=session_id,
                success=success,
                error_type=error_type,
                search_results_count=search_count,
                top_similarity_score=top_score,
                cache_hit=result.get("from_cache", False),
                llm_backend=os.getenv("LLM_BACKEND", "qwen72b"),
                llm_tokens=result.get("tokens", 0),
            )
        except Exception as e:
            logger.warning(f"⚠️ 대화 로깅 실패 (무시): {e}")

    def _evaluate_result(
        self,
        result: dict[str, Any],
        mode: str,
        elapsed_ms: int,
        search_count: int
    ) -> tuple[bool, Optional[str]]:
        """응답 성공/실패 판정

        Args:
            result: 응답 딕셔너리
            mode: 처리 모드
            elapsed_ms: 응답 시간 (밀리초)
            search_count: 검색 결과 개수

        Returns:
            (success, error_type) 튜플
        """
        answer_text = result.get("text", "")

        # 실패 케이스 감지
        if not answer_text or answer_text.strip() == "":
            return False, "no_answer"

        if elapsed_ms > PipelineConfig.ANSWER_TIMEOUT_MS:
            return True, "timeout"  # 응답은 있지만 느림

        if search_count == 0 and mode in ["search", "document"]:
            return True, "no_results"

        if answer_text.startswith("{") and "keywords" in answer_text:
            # LLM 환각 감지 (JSON 출력)
            return False, "llm_hallucination"

        return True, None


__all__ = ["ConversationService"]
