"""
LLM 모델 정의 및 기본 클래스 v1.1

GenerationConfig, RAGResponse 데이터 클래스 및 BaseRAGLLM 기본 클래스.

2025-11-28: llm_wrapper.py에서 분리
2025-12-21 v1.1: LLMGenerationConfig로 설정 외부화, H100 최적화
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from config.constants import LLMGenerationConfig

# Generation 설정 상수 (LLMGenerationConfig에서 참조)
DEFAULT_TEMPERATURE = LLMGenerationConfig.DEFAULT_TEMPERATURE
DEFAULT_MAX_TOKENS = LLMGenerationConfig.DEFAULT_MAX_TOKENS
DEFAULT_TOP_P = LLMGenerationConfig.DEFAULT_TOP_P
DEFAULT_TOP_K = LLMGenerationConfig.DEFAULT_TOP_K
DEFAULT_REPEAT_PENALTY = LLMGenerationConfig.DEFAULT_REPEAT_PENALTY
MAX_LLM_RETRY = int(os.getenv("MAX_LLM_RETRY", "1"))  # .env에서 읽기

# 적응형 길이 설정 상수
ADAPTIVE_LENGTH_ENABLED = LLMGenerationConfig.ADAPTIVE_LENGTH_ENABLED
LENGTH_PREFERENCE_DEFAULT = LLMGenerationConfig.LENGTH_PREFERENCE_DEFAULT
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
    length_adjustments: Optional[list[str]] = None
    adaptive_length_used: bool = False


# 토큰 예산 단일 설정 (LLMGenerationConfig에서 참조, H100 최적화)
_cfg = LLMGenerationConfig
MODE_TOKEN_CONFIG = {
    "chat": {"max": _cfg.MODE_CHAT_MAX, "context": _cfg.MODE_CHAT_CONTEXT},
    "rag": {"max": _cfg.MODE_RAG_MAX, "context": _cfg.MODE_RAG_CONTEXT},  # H100: 4096/6000
    "summarize": {"max": _cfg.MODE_SUMMARIZE_MAX, "context": _cfg.MODE_SUMMARIZE_CONTEXT},
    "full_document": {"max": _cfg.MODE_FULL_DOC_MAX, "context": _cfg.MODE_FULL_DOC_CONTEXT},
    "conversational": {"max": _cfg.MODE_CONVERSATIONAL_MAX, "context": _cfg.MODE_CONVERSATIONAL_CONTEXT},
    "default": {"max": _cfg.MODE_DEFAULT_MAX, "context": _cfg.MODE_DEFAULT_CONTEXT},
}


class BaseRAGLLM:
    """RAG LLM 베이스 클래스 - 공통 기능 제공"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.length_analyzer = None  # 명시적 초기화

    def _get_chunk_source(self, chunk: dict[str, Any]) -> str:
        """청크에서 소스 정보 추출 (공통 유틸리티)

        우선순위:
        1. 직접 필드: source, filename, file_path, doc_id
        2. metadata 딕셔너리: metadata.source, metadata.filename, metadata.file_path
        3. meta 딕셔너리: meta.source, meta.filename, meta.doc_id
        4. 빈 문자열 (폴백)
        """
        # 1. 직접 필드 검색
        result = (chunk.get("source")
                  or chunk.get("filename")
                  or chunk.get("file_path")
                  or chunk.get("doc_id"))
        if result:
            return result

        # 2. metadata 딕셔너리 검색
        metadata = chunk.get("metadata", {})
        if isinstance(metadata, dict):
            result = (metadata.get("source")
                      or metadata.get("filename")
                      or metadata.get("file_path"))
            if result:
                return result

        # 3. meta 딕셔너리 검색 (V2 어댑터 형식)
        meta = chunk.get("meta", {})
        if isinstance(meta, dict):
            result = (meta.get("source")
                      or meta.get("filename")
                      or meta.get("file_path")
                      or meta.get("doc_id"))
            if result:
                return result

        return ""

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
