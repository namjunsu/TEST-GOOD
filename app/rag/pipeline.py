"""RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

from dataclasses import dataclass, field
from typing import Protocol, List, Optional, Dict, Any

from app.core.logging import get_logger
from app.core.errors import ModelError, SearchError, ErrorCode, ERROR_MESSAGES

logger = get_logger(__name__)


# ============================================================================
# Request / Response 데이터 클래스
# ============================================================================

@dataclass
class RAGRequest:
    """RAG 요청 파라미터

    Attributes:
        query: 사용자 질문
        top_k: 검색 결과 개수
        compression_ratio: 컨텍스트 압축 비율 (0.0~1.0)
        use_hyde: HyDE 사용 여부
        temperature: LLM 생성 온도
    """
    query: str
    top_k: int = 5
    compression_ratio: float = 0.7
    use_hyde: bool = False
    temperature: float = 0.1


@dataclass
class RAGResponse:
    """RAG 응답 결과

    Attributes:
        answer: 생성된 답변
        source_docs: 참고 문서 목록 (하위 호환)
        evidence_chunks: Evidence용 정규화 청크 (권장)
        latency: 전체 실행 시간 (초)
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        metrics: 내부 지표 (검색/압축/생성 시간 등)
    """
    answer: str
    source_docs: List[str] = field(default_factory=list)
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)
    latency: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)


# ============================================================================
# 프로토콜 정의 (의존성 역전)
# ============================================================================

class Retriever(Protocol):
    """검색 엔진 인터페이스"""

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """검색 수행 (정규화 스키마 반환)

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict
                }, ...
            ]
        """
        ...


class Compressor(Protocol):
    """컨텍스트 압축기 인터페이스"""

    def compress(self, chunks: List[Dict[str, Any]], ratio: float) -> List[Dict[str, Any]]:
        """문서 압축

        Args:
            chunks: 원본 청크 목록 (정규화된 dict)
            ratio: 압축 비율

        Returns:
            압축된 청크 목록 (동일 스키마)
        """
        ...


class Generator(Protocol):
    """LLM 생성기 인터페이스"""

    def generate(self, query: str, context: str, temperature: float) -> str:
        """답변 생성

        Args:
            query: 사용자 질문
            context: 참고 문서
            temperature: 생성 온도

        Returns:
            생성된 답변
        """
        ...


# ============================================================================
# RAG 파이프라인 (파사드)
# ============================================================================

class RAGPipeline:
    """RAG 파이프라인 파사드

    검색 → 압축 → 생성을 단일 인터페이스로 제공.
    내부 구현은 Retriever/Compressor/Generator에 위임.

    Example:
        >>> pipeline = RAGPipeline()
        >>> response = pipeline.query("질문", top_k=5)
        >>> if response.success:
        ...     print(response.answer)
        ...     print(f"참고: {response.source_docs}")
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        compressor: Optional[Compressor] = None,
        generator: Optional[Generator] = None,
    ):
        """RAG 파이프라인 초기화

        Args:
            retriever: 검색 엔진 (None이면 기본 HybridRetriever 사용)
            compressor: 압축기 (None이면 기본 ContextCompressor 사용)
            generator: LLM 생성기 (None이면 기본 LlamaCppGenerator 사용)
        """
        self.retriever = retriever or self._create_default_retriever()
        self.compressor = compressor or self._create_default_compressor()
        self.generator = generator or self._create_default_generator()

        logger.info("RAG Pipeline initialized")

    def query(
        self,
        query: str,
        top_k: int = 5,
        compression_ratio: float = 0.7,
        use_hyde: bool = False,
        temperature: float = 0.1,
    ) -> RAGResponse:
        """RAG 질의 (단일 진입점)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수
            compression_ratio: 압축 비율
            use_hyde: HyDE 사용 여부
            temperature: LLM 생성 온도

        Returns:
            RAGResponse: 답변 + 메타데이터
        """
        import time

        # 입력 검증
        if not query or not query.strip():
            return RAGResponse(
                answer="",
                success=False,
                error="빈 질문입니다",
            )

        start_time = time.perf_counter()
        metrics = {}

        try:
            # 1. 검색: 정규화된 청크(dict) 리스트 기대
            search_start = time.perf_counter()
            results = self.retriever.search(query, top_k)
            metrics["search_time"] = time.perf_counter() - search_start

            if not results:
                logger.warning(f"No results found for query: {query[:50]}")
                return RAGResponse(
                    answer="관련 문서가 검색되지 않았다.",
                    success=True,
                    latency=time.perf_counter() - start_time,
                    metrics=metrics,
                )

            # 2. 압축: 청크 단위 유지(페이지/스니펫/메타 보존)
            compress_start = time.perf_counter()
            compressed = self.compressor.compress(results, compression_ratio)
            metrics["compress_time"] = time.perf_counter() - compress_start

            # 3. 생성: 컨텍스트는 스니펫 집합으로 구성
            gen_start = time.perf_counter()
            context = "\n\n".join([c.get("snippet", "") for c in compressed])
            answer = self.generator.generate(query, context, temperature)
            metrics["generate_time"] = time.perf_counter() - gen_start

            total_latency = time.perf_counter() - start_time
            metrics["total_time"] = total_latency

            logger.info(
                f"RAG query completed in {total_latency:.2f}s "
                f"(search={metrics['search_time']:.2f}s, "
                f"compress={metrics['compress_time']:.2f}s, "
                f"generate={metrics['generate_time']:.2f}s)"
            )

            return RAGResponse(
                answer=answer,
                source_docs=[c.get("doc_id") for c in results[:3]],
                evidence_chunks=compressed,  # UI용 근거
                latency=total_latency,
                success=True,
                metrics=metrics,
            )

        except SearchError as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_RETRIEVE] 검색 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except ModelError as e:
            logger.error(f"Model inference failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_GENERATE] 생성 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_UNKNOWN] {str(e)}",
                latency=time.perf_counter() - start_time,
            )

    def answer(self, query: str, top_k: Optional[int] = None) -> dict:
        """답변 생성 (Evidence 포함 구조화된 응답)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수 (None이면 기본값 5)

        Returns:
            dict: {
                "text": 답변 텍스트,
                "evidence": [
                    {
                        "doc_id": 문서 ID,
                        "page": 페이지 번호,
                        "snippet": 발췌문,
                        "meta": {"doc_id": str, "page": int, ...}
                    }, ...
                ]
            }
        """
        response = self.query(query, top_k=top_k or 5)

        if response.success:
            # 검색/압축에서 넘어온 정규화 청크 사용 (실제 page/snippet/meta 노출)
            evidence = [
                {
                    "doc_id": c.get("doc_id"),
                    "page": c.get("page", 1),
                    "snippet": c.get("snippet", ""),
                    "meta": c.get("meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}),
                }
                for c in (response.evidence_chunks or [])
            ]
            return {
                "text": response.answer,
                "evidence": evidence
            }
        else:
            # 에러 발생 시 (중립 톤, 사과 표현 금지)
            error_msg = ERROR_MESSAGES.get(ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다.")
            if response.error:
                error_msg = f"{error_msg}\n\n상세: {response.error}"

            return {
                "text": error_msg,
                "evidence": []
            }

    def answer_text(self, query: str) -> str:
        """답변 텍스트만 반환 (하위 호환성)

        Args:
            query: 사용자 질문

        Returns:
            str: 생성된 답변 텍스트
        """
        result = self.answer(query)
        return result["text"]

    def warmup(self) -> None:
        """워밍업: LLM + 인덱스 사전 로딩

        첫 쿼리 지연 제거를 위해 시작 시 호출.
        """
        logger.info("Warming up RAG pipeline...")
        try:
            # 더미 쿼리 실행
            response = self.query("test warmup query", top_k=1)
            if response.success:
                logger.info(f"Warmup completed in {response.latency:.2f}s")
            else:
                logger.warning(f"Warmup failed: {response.error}")
        except Exception as e:
            logger.error(f"Warmup error: {e}", exc_info=True)

    # ========================================================================
    # 내부 헬퍼: 기본 구현 생성
    # ========================================================================

    def _create_default_retriever(self) -> Retriever:
        """기본 검색 엔진 생성 (HybridRetriever)"""
        try:
            from app.rag.retrievers.hybrid import HybridRetriever
            retriever = HybridRetriever()
            logger.info("Default HybridRetriever 생성 완료")
            return retriever
        except Exception as e:
            logger.error(f"HybridRetriever 생성 실패: {e}")
            # 폴백: 더미 구현
            return _DummyRetriever()

    def _create_default_compressor(self) -> Compressor:
        """기본 압축기 생성 (현재는 no-op)"""
        logger.info("Default compressor 생성 (no-op)")
        return _NoOpCompressor()

    def _create_default_generator(self) -> Generator:
        """기본 LLM 생성기 생성 (레거시 어댑터 사용)"""
        try:
            # 레거시 구현 어댑터 사용 (점진적 이관 준비)
            legacy_rag = self._create_legacy_adapter()
            logger.info("Default generator 생성 (Legacy Adapter 래핑)")
            return _QuickFixGenerator(legacy_rag)
        except Exception as e:
            logger.error(f"Generator 생성 실패: {e}")
            return _DummyGenerator()

    def _create_legacy_adapter(self):
        """레거시 구현 어댑터 생성 (캡슐화)

        QuickFixRAG를 래핑하여 기존 레거시 시스템과 연결합니다.
        향후 이 메서드만 수정하여 신규 구현으로 점진 전환 가능.

        Returns:
            QuickFixRAG: 레거시 RAG 인스턴스
        """
        from quick_fix_rag import QuickFixRAG

        # 레거시 시스템 초기화
        logger.info("Loading legacy QuickFixRAG adapter...")
        rag = QuickFixRAG(use_hybrid=True)
        logger.info("Legacy adapter loaded successfully")

        return rag


# ============================================================================
# 폴백 구현 (기본 동작 보장)
# ============================================================================

class _DummyRetriever:
    """더미 검색기 (폴백용)"""

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        logger.warning("Dummy retriever: 빈 결과 반환")
        return []


class _NoOpCompressor:
    """No-op 압축기 (압축하지 않음)"""

    def compress(self, chunks: List[Dict[str, Any]], ratio: float) -> List[Dict[str, Any]]:
        logger.debug("No-op compressor: 압축 스킵")
        return chunks


class _QuickFixGenerator:
    """QuickFixRAG 래퍼 (기존 구현 활용)"""

    def __init__(self, rag):
        self.rag = rag

    def generate(self, query: str, context: str, temperature: float) -> str:
        # 재검색 금지. 컨텍스트 기반 생성으로 우선 시도.
        try:
            # 1) QuickFixRAG에 전용 메서드가 있으면 사용
            if hasattr(self.rag, "generate_from_context"):
                return self.rag.generate_from_context(query, context, temperature=temperature)
            # 2) 내부 LLM 직접 접근 경로가 있으면 사용
            if hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response"):
                # context는 "\n\n"로 조인된 스니펫 문자열
                # CRITICAL FIX: generate_response returns RAGResponse object, extract .answer
                response = self.rag.llm.generate_response(query, context)
                # Handle both RAGResponse object and string returns
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)
            # 3) 폴백: 재검색이 포함된 answer는 최후 수단으로만
            logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")
            return self.rag.answer(query, use_llm_summary=True)
        except Exception as e:
            logger.error(f"Generation 실패: {e}")
            return f"[E_GENERATE] {str(e)}"


class _DummyGenerator:
    """더미 생성기 (폴백용)"""

    def generate(self, query: str, context: str, temperature: float) -> str:
        logger.warning("Dummy generator: 기본 응답 반환")
        return "죄송합니다. 답변을 생성할 수 없습니다."
