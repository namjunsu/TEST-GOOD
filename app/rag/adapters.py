"""RAG 어댑터 및 폴백 구현

이 모듈은 RAG 파이프라인의 어댑터와 폴백 클래스를 제공합니다:
- _LLMAdapter: QwenLLM 래퍼
- _QuickFixGenerator: QuickFixRAG 래퍼
- _V2RetrieverAdapter: V2 검색기 어댑터
- _DummyRetriever/_NoOpCompressor/_DummyGenerator: 폴백 구현

의존성: contracts (Protocol), logger
"""

from dataclasses import dataclass
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


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

    def generate_from_context(self, query: str, context: str, temperature: float = 0.1, mode: str = "rag") -> str:
        """컨텍스트 기반 답변 생성

        Args:
            query: 사용자 질문
            context: 검색된 문서 컨텍스트 (텍스트 형식)
            temperature: 생성 온도
            mode: 생성 모드 (chat/rag/summarize)

        Returns:
            str: 생성된 답변
        """
        # 🔥 컨텍스트 크기 제한 (LLM n_ctx=4096 기준, 프롬프트+응답 여유 확보)
        # 한글 토큰당 ~1.3자, 2500토큰 = ~3250자
        MAX_CONTEXT_CHARS = 3000
        if len(context) > MAX_CONTEXT_CHARS:
            logger.info(f"⚠️ 컨텍스트 잘림: {len(context)} → {MAX_CONTEXT_CHARS}자")
            context = context[:MAX_CONTEXT_CHARS]

        # Context를 청크 형식으로 변환
        chunks = [{"snippet": context, "content": context}]

        try:
            # 🎯 모드별 토큰 예산 적용
            logger.info(f"🎯 generate_from_context: mode={mode}")
            response = self.llm.generate_response(query, chunks, max_retries=1, mode=mode)

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

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        """답변 생성 (재검색 금지, 컨텍스트 기반 우선)"""
        try:
            # Strategy 1: 전용 메서드 사용
            result = self._try_generate_from_context(query, context, temperature, mode)
            if result is not None:
                return result

            # Strategy 2: 내부 LLM 직접 접근
            result = self._try_direct_llm(query, context, mode)
            if result is not None:
                return result

            # Strategy 3: 폴백 (재검색 포함)
            return self._fallback_answer(query)

        except Exception as e:
            logger.error(f"Generation 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {e!s}"

    def _try_generate_from_context(
        self, query: str, context: str, temperature: float, mode: str
    ) -> Optional[str]:
        """Strategy 1: generate_from_context 메서드 시도"""
        if hasattr(self.rag, "generate_from_context"):
            return self.rag.generate_from_context(
                query, context, temperature=temperature, mode=mode
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

        response = self.rag.llm.generate_response(query, chunks, max_retries=1, mode=mode)

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

    def _fallback_answer(self, query: str) -> str:
        """Strategy 3: 폴백 (재검색 포함)"""
        logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")

        if self.rag is None:
            logger.error("QuickFixRAG 없음: 답변 생성 불가")
            return AdapterConfig.ERROR_RAG_UNAVAILABLE

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

            logger.info(f"V2 Adapter: {len(v1_results)} results converted")
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
