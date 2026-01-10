"""RAG 어댑터 및 폴백 구현

이 모듈은 RAG 파이프라인의 어댑터와 폴백 클래스를 제공합니다:
- _LLMAdapter: QwenLLM 래퍼
- _QuickFixGenerator: QuickFixRAG 래퍼
- _V2RetrieverAdapter: V2 검색기 어댑터
- _DummyRetriever/_NoOpCompressor/_DummyGenerator: 폴백 구현

의존성: contracts (Protocol), logger
"""

import os
from dataclasses import dataclass
from typing import Any, Optional

from app.core.logging import get_logger
from app.prompts.document_prompts import build_qa_prompt, COMMON_RULES
from app.rag.token_allocator import get_token_allocator
from config.constants import LLMConfig, TokenConfig

logger = get_logger(__name__)

# ============================================================================
# 환경변수 기반 토큰 예산 (모듈 로드 시 1회만 읽음)
# ============================================================================

# 2026-01-10: TokenConfig로 통합 (Single Source of Truth)
MODE_TOKEN_BUDGETS: dict[str, int] = {
    "chat": TokenConfig.CHAT,
    "rag": TokenConfig.RAG,
    "qa": TokenConfig.QA,
    "detailed": TokenConfig.DETAILED,
    "summarize": TokenConfig.SUMMARIZE,
    "summary": TokenConfig.SUMMARY,
    "year_summary": TokenConfig.YEAR_SUMMARY,
    "comprehensive_report": TokenConfig.COMPREHENSIVE_REPORT,
}

RAG_MAX_CONTEXT_CHARS: int = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000"))


# ============================================================================
# 상수 설정
# ============================================================================


@dataclass(frozen=True)
class AdapterConfig:
    """어댑터 설정 상수"""

    # Snippet 길이 설정
    SNIPPET_MIN_LENGTH: int = 50
    SNIPPET_MAX_LENGTH: int = 500

    # 에러 메시지 (중립 톤)
    ERROR_GENERATOR_DISABLED: str = "[E_GENERATE] 현재 생성기가 비활성 상태입니다."
    ERROR_RAG_UNAVAILABLE: str = "[E_GENERATE] RAG 시스템을 사용할 수 없습니다."


# ============================================================================
# 폴백 구현 (기본 동작 보장)
# ============================================================================


class _DummyRetriever:
    """더미 검색기 (폴백용)"""

    def search(
        self,
        query: str,
        top_k: int,
        *,
        mode: str = "chat",
        selected_filename: Optional[str] = None,
        strict_content: bool = False,
    ) -> list[dict[str, Any]]:
        logger.warning("Dummy retriever: 빈 결과 반환")
        return []


class _NoOpCompressor:
    """No-op 압축기 (압축하지 않음)"""

    def compress(
        self, chunks: list[dict[str, Any]], ratio: float,
    ) -> list[dict[str, Any]]:
        logger.debug("No-op compressor: 압축 스킵")
        return chunks


class _DummyGenerator:
    """더미 생성기 (폴백용)"""

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        logger.warning("Dummy generator: 기본 응답 반환")
        return AdapterConfig.ERROR_GENERATOR_DISABLED


# ============================================================================
# 어댑터 구현
# ============================================================================


class _LLMAdapter:
    """QwenLLM 어댑터 (LegacyAdapter 대체)

    QwenLLM을 _QuickFixGenerator가 기대하는 인터페이스로 변환합니다.
    """

    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def generate_from_context(
        self,
        query: str,
        context: str,
        temperature: float = 0.1,
        mode: str = "rag",
        system_msg: Optional[str] = None,
        max_tokens: Optional[int] = None,  # 2025-12-23: 동적 토큰 지원
        detail_level: str = "normal",  # 2026-01-06: 상세도 기반 토큰 조정
        metadata: Optional[dict[str, str]] = None,  # 2026-01-09: 메타데이터 전달
    ) -> str:
        """컨텍스트 기반 답변 생성

        Args:
            query: 사용자 질문 (완전한 프롬프트 형식)
            context: 검색된 문서 컨텍스트 (텍스트 형식) - 이미 query에 포함된 경우 무시됨
            temperature: 생성 온도
            mode: 생성 모드 (chat/rag/summarize/detailed)
            system_msg: 시스템 프롬프트 (None이면 기본값 사용)
            max_tokens: 최대 생성 토큰 (None이면 모드 기반 기본값 사용)
            detail_level: 답변 상세도 ("brief", "normal", "detailed")
            metadata: 문서 메타데이터 (filename, drafter, date)

        Returns:
            str: 생성된 답변
        """
        # 2026-01-10: 동적 토큰 할당 (SmartTokenAllocator 사용)
        if max_tokens is None:
            # mode에서 detail_level suffix 추출 (예: "qa_brief" → "brief")
            mode_parts = mode.lower().split("_")
            base_mode = mode_parts[0]
            embedded_detail = mode_parts[1] if len(mode_parts) > 1 and mode_parts[1] in ["brief", "normal", "detailed"] else None

            # embedded detail이 있으면 우선 사용, 없으면 파라미터 사용
            effective_detail = embedded_detail or detail_level

            # SmartTokenAllocator 사용
            allocator = get_token_allocator()
            context_len = len(context) if context else 0
            query_complexity = allocator.estimate_complexity(query)

            # 동적 할당
            max_tokens = allocator.allocate(
                mode=base_mode,
                context_len=context_len,
                query_complexity=query_complexity
            )

            # detail_level 추가 조정
            if effective_detail == "brief":
                max_tokens = int(max_tokens * 0.5)  # 50% 감소
            elif effective_detail == "detailed":
                max_tokens = int(max_tokens * 1.5)  # 50% 증가

            logger.debug(
                f"동적 토큰 할당: mode={base_mode} detail={effective_detail} "
                f"context_len={context_len} complexity={query_complexity:.2f} → {max_tokens}"
            )

        # 🔧 2025-12-16: 모드별 시스템 프롬프트 (외부 전달 우선)
        # 2026-01-09: COMMON_RULES 추가로 프롬프트 인젝션 차단 및 규칙 강화
        if system_msg is None:
            system_msg = f"""당신은 문서 분석 전문가입니다. 문서 내용을 기반으로 정확하게 답변하세요.

{COMMON_RULES}

모든 답변은 위 규칙을 엄격히 준수해야 합니다."""

        # 2025-12-26: source/resolver 추적 로깅 (디버깅 강화)
        env_key = f"{mode.upper()}_MAX_TOKENS"
        logger.debug(
            f"generate mode={mode} max_tokens={max_tokens} "
            f"(source=MODE_TOKEN_BUDGETS env_key={env_key})"
        )

        try:
            # 🔧 2025-12-16: llama_cpp 직접 호출로 이중 프롬프트 문제 해결
            # generate_response()는 create_user_prompt()로 프롬프트를 다시 감싸므로,
            # document_handler가 이미 완전한 프롬프트를 제공한 경우 직접 호출 필요
            llm_instance = getattr(self.llm, "llm", None)

            # 🔧 2025-12-21: vLLM vs llama_cpp 분기 처리
            # vLLM은 create_chat_completion 미지원, generate_response() 사용
            is_vllm = hasattr(self.llm, "__class__") and "Vllm" in self.llm.__class__.__name__

            if is_vllm:
                # vLLM: generate_response() 사용 (직접 호출 불가)
                # 2025-12-23: max_tokens 동적 전달 (응답 잘림 버그 수정)
                # 2026-01-09: 프롬프트 템플릿 적용 (QA_PROMPT + COMMON_RULES)
                logger.debug(f"vLLM 모드: generate_response() 사용 (max_tokens={max_tokens})")

                # 프롬프트 템플릿 구성 (context가 있을 때만)
                if context and context.strip():
                    # 2026-01-09: 메타데이터 포함
                    meta = metadata or {}
                    full_prompt = build_qa_prompt(
                        context=context,
                        query=query,
                        filename=meta.get("filename", ""),
                        drafter=meta.get("drafter", ""),
                        date=meta.get("date", "")
                    )
                    logger.debug(f"프롬프트 템플릿 적용: QA_PROMPT (context={len(context)}자, query={len(query)}자, metadata={bool(meta)})")
                else:
                    full_prompt = query
                    logger.debug(f"프롬프트 템플릿 미적용: context 없음")

                # chunks는 빈 리스트로 전달 (이미 full_prompt에 context 포함)
                response = self.llm.generate_response(full_prompt, [], max_tokens=max_tokens)
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

            if llm_instance is not None and hasattr(llm_instance, "create_chat_completion"):
                # llama_cpp: 직접 호출 가능
                # 🔧 2025-12-16: RAG 모드에서는 context를 user prompt에 포함해야 함
                # 2026-01-09: 프롬프트 템플릿 적용 (QA_PROMPT + COMMON_RULES)
                query_has_context = any(marker in query for marker in [
                    "참고 문서", "Context:", "[문서 내용]", "### 문서", "문서 정보:",
                ])

                if context and context.strip() and not query_has_context:
                    # context가 별도로 제공된 경우 → 프롬프트 템플릿 적용
                    # 2026-01-09: 메타데이터 포함
                    meta = metadata or {}
                    user_content = build_qa_prompt(
                        context=context,
                        query=query,
                        filename=meta.get("filename", ""),
                        drafter=meta.get("drafter", ""),
                        date=meta.get("date", "")
                    )
                    logger.debug(f"프롬프트 템플릿 적용: QA_PROMPT (llama_cpp, context={len(context)}자, metadata={bool(meta)})")
                else:
                    user_content = query
                    logger.debug(f"프롬프트 템플릿 미적용: query_has_context={query_has_context}")

                # llama_cpp.Llama 직접 접근
                output = llm_instance.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = output["choices"][0]["message"].get("content")
                answer = content.strip() if content else ""
                return answer

            # 폴백: generate_response() 사용 (이중 프롬프트 문제 있을 수 있음)
            logger.warning("⚠️ llama_cpp 직접 접근 불가, generate_response() 폴백")
            chunks = [{"snippet": context, "content": context}]
            # Qwen72BLLM은 max_retries, mode 인자를 지원하지 않음
            response = self.llm.generate_response(query, chunks)

            if hasattr(response, "answer"):
                return response.answer
            return str(response)

        except Exception as e:
            logger.error(f"LLM 답변 생성 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {e!s}"


class _QuickFixGenerator:
    """QuickFixRAG 래퍼 (기존 구현 활용)

    생성 전략 우선순위:
    1. generate_from_context (직접 컨텍스트 기반)
    2. llm.generate_response (내부 LLM 직접 접근)
    3. answer (폴백, 재검색 포함)
    """

    def __init__(self, rag: Any) -> None:
        self.rag = rag
        self.compressed_chunks: Optional[list[dict[str, Any]]] = None

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag", metadata: Optional[dict[str, str]] = None) -> str:
        """답변 생성 (재검색 금지, 컨텍스트 기반 우선)

        Args:
            metadata: 문서 메타데이터 (2026-01-09 추가)
        """
        try:
            # Strategy 1: 전용 메서드 사용
            result = self._try_generate_from_context(query, context, temperature, mode, metadata)
            if result is not None:
                return result

            # Strategy 2: 내부 LLM 직접 접근
            result = self._try_direct_llm(query, context, mode)
            if result is not None:
                return result

            # Strategy 3: 폴백 (컨텍스트 인지, 2026-01-10)
            return self._fallback_answer(query, context)

        except Exception as e:
            logger.error(f"Generation 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {e!s}"

    def _try_generate_from_context(
        self, query: str, context: str, temperature: float, mode: str, metadata: Optional[dict[str, str]] = None
    ) -> Optional[str]:
        """Strategy 1: generate_from_context 메서드 시도"""
        if hasattr(self.rag, "generate_from_context"):
            return self.rag.generate_from_context(
                query, context, temperature=temperature, mode=mode, metadata=metadata
            )
        return None

    def _try_direct_llm(self, query: str, context: str, mode: str) -> Optional[str]:
        """Strategy 2: 내부 LLM 직접 접근"""
        # Lazy loading 보장
        if hasattr(self.rag, "_ensure_llm_loaded"):
            self.rag._ensure_llm_loaded()

        if not (hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response")):
            return None

        # 청크 준비
        chunks = self._prepare_chunks(context)
        logger.debug(f"Using {len(chunks)} chunks for generation (mode={mode})")

        # Qwen72BLLM/VllmLLM은 max_retries, mode 인자를 지원하지 않음
        # 기본 시그니처: generate_response(query, context_chunks)
        try:
            response = self.rag.llm.generate_response(query, chunks)
        except TypeError:
            # 폴백: 추가 인자 시도
            response = self.rag.llm.generate_response(query, chunks)

        # RAGResponse에서 answer 추출
        if hasattr(response, "answer"):
            return response.answer
        return str(response)

    def _prepare_chunks(self, context: str) -> list[dict[str, Any]]:
        """LLM용 청크 준비"""
        if self.compressed_chunks:
            return self.compressed_chunks

        # 폴백: context 문자열을 청크로 변환
        logger.warning("No compressed_chunks available, converting context string")
        snippets = context.split("\n\n")
        return [{"snippet": s, "content": s} for s in snippets if s.strip()]

    def _fallback_answer(self, query: str, context: str = "") -> str:
        """Strategy 3: 폴백 (컨텍스트 인지, 2026-01-10 개선)

        Args:
            query: 사용자 질문
            context: 압축/정제된 컨텍스트 (있으면 쿼리에 포함)

        Returns:
            생성된 답변
        """
        logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")

        if self.rag is None:
            logger.error("QuickFixRAG 없음: 답변 생성 불가")
            return AdapterConfig.ERROR_RAG_UNAVAILABLE

        # 컨텍스트가 있으면 쿼리에 포함하여 정보 손실 방지
        if context:
            enriched_query = (
                f"{query}\n\n"
                f"[관련 정보]\n"
                f"{context[:2000]}"  # 처음 2000자만 사용
            )
            logger.debug(f"컨텍스트 포함 폴백 ({len(context)}자 → {len(context[:2000])}자)")
            return self.rag.answer(enriched_query, use_llm_summary=True)

        return self.rag.answer(query, use_llm_summary=True)


class _V2RetrieverAdapter:
    """V2 Retriever Adapter

    HybridRetrieverV2의 결과 형식 {"fused_results": [...]}를
    v1 인터페이스 형식 [...] 으로 변환.

    v2 results: {"fused_results": [{"id": ..., "score": ..., ...}, ...]}
    v1 expected: [{"doc_id": ..., "snippet": ..., "page": 1, ...}, ...]
    """

    def __init__(self, v2_retriever: Any) -> None:
        self.v2_retriever = v2_retriever
        self.db = v2_retriever.db

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """V2 검색 후 V1 형식으로 변환"""
        try:
            v2_result = self.v2_retriever.search(query, top_k=top_k)
            fused_results = v2_result.get("fused_results", [])

            v1_results = [self._convert_doc(doc) for doc in fused_results]

            logger.debug(f"V2 Adapter: {len(v1_results)} results converted")
            return v1_results

        except Exception as e:
            logger.error(f"V2 Adapter search failed: {e}", exc_info=True)
            return []

    def _convert_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """단일 문서를 V1 형식으로 변환"""
        doc_id = doc.get("id", "unknown")
        snippet = self._resolve_snippet(doc, doc_id)

        return {
            "doc_id": doc_id,
            "snippet": snippet,
            "page": 1,
            "score": doc.get("score", 0.0),
            "meta": {
                "doc_id": doc_id,
                "filename": doc.get("filename", ""),
                "title": doc.get("title", ""),
                "date": doc.get("date", ""),
                "page": 1,
            },
        }

    def _resolve_snippet(self, doc: dict[str, Any], doc_id: str) -> str:
        """Snippet 해결 (우선순위: 직접 포함 → DB 조회 → 메타데이터 폴백)"""
        max_len = AdapterConfig.SNIPPET_MAX_LENGTH
        min_len = AdapterConfig.SNIPPET_MIN_LENGTH

        # Priority 1: 검색 결과에 직접 포함
        snippet = doc.get("snippet") or ""
        if not snippet and "content" in doc:
            snippet = doc["content"][:max_len]

        # Priority 2: DB 조회
        if len(snippet) < min_len:
            content = self.db.get_content(doc_id)
            if content and len(content) >= min_len:
                snippet = content[:max_len]

        # Priority 3: 메타데이터 폴백
        if len(snippet) < min_len:
            snippet = self._build_metadata_fallback(doc, doc_id)

        return snippet

    def _build_metadata_fallback(self, doc: dict[str, Any], doc_id: str) -> str:
        """메타데이터 기반 폴백 snippet 생성"""
        parts = []
        if doc.get("title"):
            parts.append(f"제목: {doc['title']}")
        if doc.get("filename"):
            parts.append(f"파일: {doc['filename']}")
        if doc.get("date"):
            parts.append(f"날짜: {doc['date']}")

        if parts:
            logger.warning(f"V2 Adapter: doc_id={doc_id} snippet 결손, 메타데이터 폴백")
            return " | ".join(parts)

        return f"문서 ID: {doc_id}"

    def warmup(self) -> None:
        """워밍업 (V2는 필요 시 자동 로드)"""
        logger.info("V2 Adapter warmup (no-op)")


__all__ = [
    # 설정
    "AdapterConfig",
    # 폴백 구현
    "_DummyGenerator",
    "_DummyRetriever",
    "_NoOpCompressor",
    # 어댑터
    "_LLMAdapter",
    "_QuickFixGenerator",
    "_V2RetrieverAdapter",
]
