"""대화 로깅 시스템 v1.1

- 사용자 질문 + AI 답변 + 출처 문서 기록
- 일별 JSONL 파일로 저장
- 답변 품질 분석 및 개선에 활용

2025-12-16: 초기 구현
2025-12-21 v1.1: ConversationLoggerConfig로 설정 외부화
"""

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.logging import get_logger
from config.constants import ConversationLoggerConfig

logger = get_logger(__name__)


@dataclass
class ConversationEntry:
    """대화 기록 엔트리 v2.0 - 디버깅 강화"""
    # 기본 정보 (기존)
    timestamp: str
    query: str
    mode: str  # search, document, qa, cost
    answer: str
    sources: list[str] = field(default_factory=list)  # 출처 파일명 목록
    confidence: float = 0.0
    latency_ms: int = 0  # 응답 시간 (밀리초)

    # 사용자 구분 (NEW)
    client_ip: Optional[str] = None  # 접속 IP
    session_id: Optional[str] = None  # Streamlit 세션 ID

    # 성공/실패 추적 (NEW)
    success: bool = True  # 답변 성공 여부
    error_type: Optional[str] = None  # "timeout", "no_results", "llm_error", "search_error"

    # 검색 품질 (NEW)
    search_results_count: int = 0  # 검색된 문서 개수
    top_similarity_score: float = 0.0  # 최상위 결과 유사도

    # 캐시 정보 (NEW)
    cache_hit: bool = False  # 캐시 히트 여부

    # LLM 정보 (NEW)
    llm_backend: Optional[str] = None  # "qwen72b", "vllm"
    llm_tokens: int = 0  # 생성된 토큰 수


class ConversationLogger:
    """대화 로깅"""

    def __init__(self, log_dir: str = ConversationLoggerConfig.LOG_DIR):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"💬 대화 로거 초기화: {self.log_dir}")

    def _get_log_file(self) -> Path:
        """일별 로그 파일 경로"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"conv_{today}.jsonl"

    def log(
        self,
        query: str,
        answer: str,
        mode: str,
        sources: Optional[list[dict[str, Any]]] = None,
        confidence: float = 0.0,
        latency_ms: int = 0,
        # NEW 파라미터들
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        success: bool = True,
        error_type: Optional[str] = None,
        search_results_count: int = 0,
        top_similarity_score: float = 0.0,
        cache_hit: bool = False,
        llm_backend: Optional[str] = None,
        llm_tokens: int = 0,
    ) -> None:
        """대화 기록 저장 v2.0

        Args:
            query: 사용자 질문
            answer: AI 답변
            mode: 라우팅 모드
            sources: 출처 문서 목록 (evidence 리스트)
            confidence: 라우팅 신뢰도
            latency_ms: 응답 시간 (밀리초)
            client_ip: 클라이언트 IP 주소
            session_id: Streamlit 세션 ID
            success: 답변 성공 여부
            error_type: 에러 타입 ("timeout", "no_results", "llm_error", "search_error")
            search_results_count: 검색된 문서 개수
            top_similarity_score: 최상위 검색 결과 유사도
            cache_hit: 캐시 히트 여부
            llm_backend: 사용된 LLM 백엔드
            llm_tokens: 생성된 토큰 수
        """
        # 출처 파일명 추출
        source_files = []
        if sources:
            for src in sources[:ConversationLoggerConfig.MAX_SOURCES]:
                if isinstance(src, dict):
                    filename = src.get("filename") or src.get("meta", {}).get("filename", "")
                    if filename:
                        source_files.append(filename)

        # 답변 길이 제한
        max_len = ConversationLoggerConfig.MAX_ANSWER_LENGTH
        answer_truncated = answer[:max_len]
        if len(answer) > max_len:
            answer_truncated += "... (truncated)"

        entry = ConversationEntry(
            timestamp=datetime.now().isoformat(),
            query=query,
            mode=mode,
            answer=answer_truncated,
            sources=source_files,
            confidence=confidence,
            latency_ms=latency_ms,
            # NEW 필드들
            client_ip=client_ip,
            session_id=session_id,
            success=success,
            error_type=error_type,
            search_results_count=search_results_count,
            top_similarity_score=top_similarity_score,
            cache_hit=cache_hit,
            llm_backend=llm_backend,
            llm_tokens=llm_tokens,
        )

        try:
            log_file = self._get_log_file()
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"대화 로그 기록 실패: {e}")

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """최근 대화 조회

        Args:
            limit: 조회할 최대 개수

        Returns:
            최근 대화 목록 (최신순)
        """
        log_file = self._get_log_file()
        if not log_file.exists():
            return []

        try:
            entries = []
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    entries.append(json.loads(line))
            return entries[-limit:][::-1]  # 최신순
        except Exception as e:
            logger.error(f"대화 로그 조회 실패: {e}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """오늘 대화 통계"""
        log_file = self._get_log_file()
        if not log_file.exists():
            return {"total": 0}

        try:
            entries = []
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    entries.append(json.loads(line))

            if not entries:
                return {"total": 0}

            from collections import Counter
            mode_counts = Counter(e["mode"] for e in entries)
            avg_latency = sum(e.get("latency_ms", 0) for e in entries) / len(entries)

            return {
                "total": len(entries),
                "mode_distribution": dict(mode_counts),
                "avg_latency_ms": round(avg_latency),
            }
        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {"error": str(e)}


# 싱글톤 인스턴스
_logger_instance: Optional[ConversationLogger] = None
_logger_lock = threading.Lock()


def get_conversation_logger() -> ConversationLogger:
    """싱글톤 대화 로거 반환 (thread-safe)"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = ConversationLogger()
    return _logger_instance
