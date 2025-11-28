"""RAG 어댑터 및 폴백 구현

이 모듈은 RAG 파이프라인의 어댑터와 폴백 클래스를 제공합니다:
- _LLMAdapter: QwenLLM 래퍼
- _QuickFixGenerator: QuickFixRAG 래퍼
- _V2RetrieverAdapter: V2 검색기 어댑터
- _DummyRetriever/_NoOpCompressor/_DummyGenerator: 폴백 구현

의존성: contracts (Protocol), logger
"""

from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


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
        return "[E_GENERATE] 현재 생성기가 비활성 상태입니다."


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
            return f"[E_GENERATE] {str(e)}"


class _QuickFixGenerator:
    """QuickFixRAG 래퍼 (기존 구현 활용)"""

    def __init__(self, rag: Any) -> None:
        self.rag = rag
        self.compressed_chunks: Optional[list[dict[str, Any]]] = None  # Store chunks for LLM

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        # 재검색 금지. 컨텍스트 기반 생성으로 우선 시도.
        try:
            # 1) QuickFixRAG에 전용 메서드가 있으면 사용
            if hasattr(self.rag, "generate_from_context"):
                return self.rag.generate_from_context(
                    query, context, temperature=temperature, mode=mode,
                )

            # 2) 내부 LLM 직접 접근 경로가 있으면 사용
            # 🔥 CRITICAL: LLM lazy loading - ensure LLM is loaded before checking
            if hasattr(self.rag, "_ensure_llm_loaded"):
                self.rag._ensure_llm_loaded()

            if hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response"):
                # CRITICAL: generate_response expects List[Dict], not str
                # Convert context string back to chunks format
                if self.compressed_chunks:
                    # Use stored compressed chunks (preferred)
                    logger.debug(
                        f"Using {len(self.compressed_chunks)} compressed chunks for generation (mode={mode})",
                    )
                    response = self.rag.llm.generate_response(
                        query, self.compressed_chunks, max_retries=1, mode=mode,
                    )
                else:
                    # Fallback: convert context string to minimal chunks
                    logger.warning(
                        "No compressed_chunks available, converting context string",
                    )
                    snippets = context.split("\n\n")
                    chunks = [
                        {"snippet": s, "content": s} for s in snippets if s.strip()
                    ]
                    response = self.rag.llm.generate_response(
                        query, chunks, max_retries=1, mode=mode,
                    )

                # Extract answer from RAGResponse object
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

            # 3) 폴백: 재검색이 포함된 answer는 최후 수단으로만
            logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")
            if self.rag is None:
                logger.error("LegacyAdapter: QuickFixRAG가 없어 답변 생성 불가")
                return "죄송합니다. 현재 답변 생성 기능이 비활성화되어 있습니다."
            return self.rag.answer(query, use_llm_summary=True)
        except Exception as e:
            logger.error(f"Generation 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {str(e)}"


class _V2RetrieverAdapter:
    """V2 Retriever Adapter

    HybridRetrieverV2의 결과 형식 {"fused_results": [...]}를
    v1 인터페이스 형식 [...] 으로 변환.

    v2 results 구조:
        {
            "fused_results": [
                {"id": "doc_4094", "score": 0.123, "filename": "...", ...},
                ...
            ]
        }

    v1 expected 구조:
        [
            {"doc_id": "doc_4094", "snippet": "...", "page": 1, ...},
            ...
        ]
    """

    def __init__(self, v2_retriever: Any) -> None:
        """
        Args:
            v2_retriever: HybridRetrieverV2 instance
        """
        self.v2_retriever = v2_retriever
        self.db = v2_retriever.db  # MetadataDB for content fetching

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search using v2 retriever, convert to v1 format

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of dicts in v1 format with keys:
            - doc_id: Document ID
            - snippet: Text snippet
            - page: Page number (default 1)
            - score: Relevance score
            - meta: Metadata dict
        """
        try:
            # Call v2 retriever
            v2_result = self.v2_retriever.search(query, top_k=top_k)
            fused_results = v2_result.get("fused_results", [])

            # Convert to v1 format
            v1_results = []
            for doc in fused_results:
                doc_id = doc.get("id", "unknown")

                # 🔥 CRITICAL: snippet 우선순위
                # 1) 검색 결과에 직접 포함된 snippet/content
                # 2) DB 조회 (get_content)
                # 3) 제목/파일명 기반 폴백

                snippet = ""

                # Priority 1: fused_results에 이미 포함된 데이터
                if "snippet" in doc:
                    snippet = doc["snippet"]
                elif "content" in doc:
                    snippet = doc["content"][:500]

                # Priority 2: DB 조회 (app/rag/db.MetadataDB.get_content)
                if not snippet or len(snippet) < 50:
                    content = self.db.get_content(doc_id)
                    if content and len(content) >= 50:
                        snippet = content[:500]

                # Priority 3: 메타데이터 폴백
                if not snippet or len(snippet) < 50:
                    fallback_parts = []
                    if doc.get("title"):
                        fallback_parts.append(f"제목: {doc['title']}")
                    if doc.get("filename"):
                        fallback_parts.append(f"파일: {doc['filename']}")
                    if doc.get("date"):
                        fallback_parts.append(f"날짜: {doc['date']}")

                    snippet = (
                        " | ".join(fallback_parts)
                        if fallback_parts
                        else f"문서 ID: {doc_id}"
                    )
                    logger.warning(
                        f"V2 Adapter: doc_id={doc_id} snippet 결손, 메타데이터 폴백 사용",
                    )

                v1_results.append(
                    {
                        "doc_id": doc_id,
                        "snippet": snippet,
                        "page": 1,  # v2에서는 page 정보 없음, 기본 1
                        "score": doc.get("score", 0.0),
                        "meta": {
                            "doc_id": doc_id,
                            "filename": doc.get("filename", ""),
                            "title": doc.get("title", ""),
                            "date": doc.get("date", ""),
                            "page": 1,
                        },
                    },
                )

            logger.info(f"V2 Adapter: {len(v1_results)} results converted")
            return v1_results

        except Exception as e:
            logger.error(f"V2 Adapter search failed: {e}", exc_info=True)
            return []

    def warmup(self) -> None:
        """워밍업 (v2는 필요 시 자동 로드)"""
        logger.info("V2 Adapter warmup (no-op)")


__all__ = [
    # 폴백
    "_DummyRetriever",
    "_NoOpCompressor",
    "_DummyGenerator",
    # 어댑터
    "_LLMAdapter",
    "_QuickFixGenerator",
    "_V2RetrieverAdapter",
]
