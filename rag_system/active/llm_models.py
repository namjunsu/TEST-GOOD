"""
LLM 모델 정의 및 기본 클래스

GenerationConfig, RAGResponse 데이터 클래스 및 BaseRAGLLM 기본 클래스.

2025-11-28: llm_wrapper.py에서 분리
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Generation 설정 상수 - L2 RAG 튜닝 (2025-10-25)
# 일관성 향상: temperature 0.7 → 0.2
# 효율성 향상: max_tokens 1200 → 512
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 512
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 40
DEFAULT_REPEAT_PENALTY = 1.1
MAX_LLM_RETRY = int(os.getenv("MAX_LLM_RETRY", "1"))  # .env에서 읽기

# 적응형 길이 설정 상수
ADAPTIVE_LENGTH_ENABLED = True
LENGTH_PREFERENCE_DEFAULT = "balanced"
LENGTH_PREFERENCES = ["concise", "balanced", "detailed"]


@dataclass
class GenerationConfig:
    """생성 설정"""
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    top_p: float = DEFAULT_TOP_P
    top_k: int = DEFAULT_TOP_K
    repeat_penalty: float = DEFAULT_REPEAT_PENALTY

    # 적응형 길이 조정 설정
    enable_adaptive_length: bool = ADAPTIVE_LENGTH_ENABLED
    length_preference: str = LENGTH_PREFERENCE_DEFAULT
    min_length_override: Optional[int] = None
    max_length_override: Optional[int] = None


@dataclass
class RAGResponse:
    """RAG 응답 구조"""
    answer: str
    sources_cited: list[str]
    confidence: float
    generation_time: float
    has_proper_citation: bool
    retry_count: int = 0

    # 적응형 길이 조정 관련 정보
    length_recommendation: Optional[Any] = None
    original_length: Optional[int] = None
    length_adjustments: list[str] = None
    adaptive_length_used: bool = False


# 토큰 예산 단일 설정 (2025-12-08: 답변 품질 개선 - 토큰 증가)
MODE_TOKEN_CONFIG = {
    "chat": {"max": 512, "context": 1024},       # 64 → 512 (일반 대화도 충분한 응답)
    "rag": {"max": 3072, "context": 4000},       # 160 → 3072 (.env RAG_MAX_TOKENS와 동기화)
    "summarize": {"max": 2048, "context": 4000}, # 1200 → 2048 (상세 요약)
    "full_document": {"max": 2048, "context": 4000},
    "conversational": {"max": 2048, "context": 4000},
    "default": {"max": 1024, "context": 2048},   # 512 → 1024
}


class BaseRAGLLM:
    """RAG LLM 베이스 클래스 - 공통 기능 제공"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.length_analyzer = None  # 명시적 초기화

    def _get_chunk_source(self, chunk: dict[str, Any]) -> str:
        """청크에서 소스 정보 추출 (공통 유틸리티)"""
        return (chunk.get("source")
                or chunk.get("filename")
                or chunk.get("file_path")
                or chunk.get("doc_id")
                or chunk.get("metadata", {}).get("source")
                or chunk.get("metadata", {}).get("filename")
                or "")

    def _format_context(self, context_chunks: list[dict[str, Any]]) -> str:
        """컨텍스트 포맷팅 (공통 로직)"""
        formatted = []
        for chunk in context_chunks:
            source = self._get_chunk_source(chunk)
            source_name = Path(source).name if source else "unknown"
            # 폴백 체인: text → content → snippet → text_preview
            content = (chunk.get("text") or chunk.get("content") or
                      chunk.get("snippet") or chunk.get("text_preview") or "")
            formatted.append(f"[{source_name}]\n{content}")
        return "\n\n".join(formatted)

    def _extract_sources(self, context_chunks: list[dict[str, Any]]) -> list[str]:
        """소스 파일명 추출 (공통 로직)"""
        sources = []
        for chunk in context_chunks:
            source = self._get_chunk_source(chunk)
            if source:
                source_name = Path(source).name
                if source_name not in sources:
                    sources.append(source_name)
        return sources

    def get_token_budget(self, mode: str = "default") -> dict[str, int]:
        """모드별 토큰 예산 반환"""
        return MODE_TOKEN_CONFIG.get(mode, MODE_TOKEN_CONFIG["default"])
