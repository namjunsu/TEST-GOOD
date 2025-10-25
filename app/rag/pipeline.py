"""RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

import os
import time
from dataclasses import dataclass, field
from typing import Protocol, List, Optional, Dict, Any

from app.core.logging import get_logger
from app.core.errors import ModelError, SearchError, ErrorCode, ERROR_MESSAGES

logger = get_logger(__name__)

# 진단 모드 설정
DIAG_RAG = os.getenv('DIAG_RAG', 'false').lower() == 'true'
DIAG_LOG_LEVEL = os.getenv('DIAG_LOG_LEVEL', 'INFO').upper()


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
        raw_results: 원본 검색 결과 (Evidence 최소 보장용)
        latency: 전체 실행 시간 (초)
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        metrics: 내부 지표 (검색/압축/생성 시간 등)
        diagnostics: 진단 정보 (DIAG_RAG=true일 때만 채워짐)
    """
    answer: str
    source_docs: List[str] = field(default_factory=list)
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)
    raw_results: List[Dict[str, Any]] = field(default_factory=list)
    latency: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)  # 진단 정보


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
        diagnostics = {}  # 진단 정보 수집

        try:
            # 1. 검색: 정규화된 청크(dict) 리스트 기대
            search_start = time.perf_counter()
            results = self.retriever.search(query, top_k)
            metrics["search_time"] = time.perf_counter() - search_start

            # [DIAG] 검색 결과 진단
            if DIAG_RAG:
                diagnostics["retrieved_k"] = len(results)
                if DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                    logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

            if not results:
                logger.warning(f"No results found for query: {query[:50]}")
                if DIAG_RAG:
                    diagnostics["mode"] = "no_results"
                    diagnostics["generate_path"] = "fallback_no_context"
                return RAGResponse(
                    answer="관련 문서가 검색되지 않았다.",
                    success=True,
                    latency=time.perf_counter() - start_time,
                    metrics=metrics,
                    diagnostics=diagnostics,
                )

            # 2. 압축: 청크 단위 유지(페이지/스니펫/메타 보존)
            compress_start = time.perf_counter()
            compressed = self.compressor.compress(results, compression_ratio)
            metrics["compress_time"] = time.perf_counter() - compress_start

            # [DIAG] 압축 후 진단
            if DIAG_RAG:
                diagnostics["after_compress_k"] = len(compressed)
                diagnostics["compression_ratio"] = compression_ratio
                if DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                    logger.info(f"[DIAG] 압축 완료: {len(results)} → {len(compressed)}개 문서")

            # 3. 생성: 컨텍스트는 스니펫 집합으로 구성
            gen_start = time.perf_counter()

            # CRITICAL: Inject compressed chunks into generator for proper LLM context
            if hasattr(self.generator, "compressed_chunks"):
                self.generator.compressed_chunks = compressed
                logger.debug(f"Injected {len(compressed)} compressed chunks into generator")

            context = "\n\n".join([c.get("snippet", "") for c in compressed])

            # [DIAG] 생성 전 컨텍스트 스냅샷
            if DIAG_RAG and DIAG_LOG_LEVEL == 'DEBUG':
                for i, c in enumerate(compressed[:3], 1):  # 상위 3개만 로그
                    logger.debug(
                        f"[DIAG] Context[{i}]: doc_id={c.get('doc_id')}, "
                        f"filename={c.get('filename', 'N/A')}, "
                        f"page={c.get('page', 0)}, "
                        f"snippet={c.get('snippet', '')[:120]}..."
                    )

            answer = self.generator.generate(query, context, temperature)
            metrics["generate_time"] = time.perf_counter() - gen_start

            # [DIAG] 생성 완료 진단
            if DIAG_RAG:
                diagnostics["mode"] = "normal"
                diagnostics["generate_path"] = "from_context"
                diagnostics["used_k"] = len(compressed)
                if DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                    logger.info(f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용")

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
                raw_results=results,  # Evidence 최소 보장용
                latency=total_latency,
                success=True,
                metrics=metrics,
                diagnostics=diagnostics,
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

            # CRITICAL: Evidence 최소 보장 (sources_cited가 비어도 검색 결과는 표시)
            evidence_injected = False
            if not evidence and response.raw_results:
                logger.info(f"Evidence empty, using raw_results[:3] as fallback")
                evidence = [
                    {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "page": 0,  # 검색 결과는 페이지 정보 없음
                        "snippet": r.get("snippet") or r.get("text_preview", "")[:500],
                        "meta": {
                            "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                            "filename": r.get("filename", ""),
                            "page": 0,
                        },
                    }
                    for r in response.raw_results[:3]
                ]
                evidence_injected = True

            # [DIAG] Evidence 진단 정보 추가
            if DIAG_RAG and response.diagnostics:
                response.diagnostics["evidence_count"] = len(evidence)
                response.diagnostics["evidence_injected"] = evidence_injected

            # 🔥 CRITICAL: status.found 플래그 - UI 판정 단일 소스
            # retrieved_count: 검색된 원본 결과 수
            # selected_count: 실제 사용된 증거 수 (evidence)
            # found: 검색 성공 여부 (evidence가 1개 이상이면 True)
            status = {
                "retrieved_count": len(response.raw_results or []),
                "selected_count": len(evidence),
                "found": len(evidence) > 0  # 🔴 유일한 판정 기준
            }

            return {
                "text": response.answer,
                "evidence": evidence,  # citations와 동일한 리스트
                "status": status,  # UI에서 이것만 확인
                "diagnostics": response.diagnostics if DIAG_RAG else {}
            }
        else:
            # 에러 발생 시 (중립 톤, 사과 표현 금지)
            error_msg = ERROR_MESSAGES.get(ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다.")
            if response.error:
                error_msg = f"{error_msg}\n\n상세: {response.error}"

            return {
                "text": error_msg,
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
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
        """기본 검색 엔진 생성 (v2 또는 v1)

        환경 변수 USE_V2_RETRIEVER로 제어:
        - true: HybridRetrieverV2 사용 (신규 2-layer 아키텍처)
        - false/없음: HybridRetriever 사용 (기존 레거시)
        """
        import os
        use_v2 = os.getenv('USE_V2_RETRIEVER', 'false').lower() == 'true'

        if use_v2:
            try:
                from app.rag.retriever_v2 import HybridRetrieverV2
                v2_retriever = HybridRetrieverV2()
                logger.info("✅ HybridRetrieverV2 (v2 신규 시스템) 생성 완료")

                # V2 adapter: fused_results → list 변환
                return _V2RetrieverAdapter(v2_retriever)
            except Exception as e:
                logger.error(f"V2 Retriever 생성 실패, v1으로 폴백: {e}")
                # 폴백: v1 사용
                use_v2 = False

        if not use_v2:
            try:
                from app.rag.retrievers.hybrid import HybridRetriever
                retriever = HybridRetriever()
                logger.info("Default HybridRetriever (v1 레거시) 생성 완료")
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
        self.compressed_chunks = None  # Store chunks for LLM

    def generate(self, query: str, context: str, temperature: float) -> str:
        # 재검색 금지. 컨텍스트 기반 생성으로 우선 시도.
        try:
            # 1) QuickFixRAG에 전용 메서드가 있으면 사용
            if hasattr(self.rag, "generate_from_context"):
                return self.rag.generate_from_context(query, context, temperature=temperature)

            # 2) 내부 LLM 직접 접근 경로가 있으면 사용
            if hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response"):
                # CRITICAL: generate_response expects List[Dict], not str
                # Convert context string back to chunks format
                if self.compressed_chunks:
                    # Use stored compressed chunks (preferred)
                    logger.debug(f"Using {len(self.compressed_chunks)} compressed chunks for generation")
                    response = self.rag.llm.generate_response(query, self.compressed_chunks, max_retries=1)
                else:
                    # Fallback: convert context string to minimal chunks
                    logger.warning("No compressed_chunks available, converting context string")
                    snippets = context.split("\n\n")
                    chunks = [{"snippet": s, "content": s} for s in snippets if s.strip()]
                    response = self.rag.llm.generate_response(query, chunks, max_retries=1)

                # Extract answer from RAGResponse object
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

            # 3) 폴백: 재검색이 포함된 answer는 최후 수단으로만
            logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")
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

    def __init__(self, v2_retriever):
        """
        Args:
            v2_retriever: HybridRetrieverV2 instance
        """
        self.v2_retriever = v2_retriever
        self.db = v2_retriever.db  # MetadataDB for content fetching

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
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

                # Priority 2: DB 조회
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

                    snippet = " | ".join(fallback_parts) if fallback_parts else f"문서 ID: {doc_id}"
                    logger.warning(f"V2 Adapter: doc_id={doc_id} snippet 결손, 메타데이터 폴백 사용")

                v1_results.append({
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
                })

            logger.info(f"V2 Adapter: {len(v1_results)} results converted")
            return v1_results

        except Exception as e:
            logger.error(f"V2 Adapter search failed: {e}", exc_info=True)
            return []

    def warmup(self):
        """워밍업 (v2는 필요 시 자동 로드)"""
        logger.info("V2 Adapter warmup (no-op)")


class _DummyGenerator:
    """더미 생성기 (폴백용)"""

    def generate(self, query: str, context: str, temperature: float) -> str:
        logger.warning("Dummy generator: 기본 응답 반환")
        return "죄송합니다. 답변을 생성할 수 없습니다."
