"""RAG 파이프라인 v2.0 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

2025-12-12 v2.0 변경사항:
- ModeResolver 클래스로 모드 결정 로직 분리
- ResponseBuilder 클래스로 응답 구성 로직 분리
- PipelineConfig로 Magic Number 외부화
- 중복 코드 제거 및 헬퍼 메서드 활용

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

import re
import sqlite3
import time
from typing import Any, Optional

from app.config.settings import settings
from app.core.errors import ERROR_MESSAGES, ErrorCode, ModelError, SearchError
from app.core.logging import get_logger
from app.rag.adapters import _LLMAdapter
from app.rag.cache_manager import build_answer_cache_key
from app.rag.contracts import Compressor, Generator, RAGResponse, Retriever
from app.rag.document_utils import DocumentUtils
from app.rag.factory import RAGPipelineFactory
from app.rag.mode_resolver import ModeResolver, get_mode_resolver
from app.rag.query_router import QueryMode, QueryRouter
from app.rag.query_routing import (
    DIAG_LOG_LEVEL,
    DIAG_RAG,
    _encode_file_ref,
    clean_ui_metadata,
)
from app.rag.response_builder import ResponseBuilder, get_response_builder
from app.rag.router_models import RouteDecision
from app.rag.services import CacheService, ConversationService
from app.rag.similarity import DocumentSimilarity
from config.constants import PipelineConfig

logger = get_logger(__name__)


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
        # 🏭 팩토리를 통한 컴포넌트 생성 (분리된 모듈)
        self.retriever = retriever or RAGPipelineFactory.create_retriever()
        self.compressor = compressor or RAGPipelineFactory.create_compressor()
        self.generator = generator or RAGPipelineFactory.create_generator()
        self.query_router = QueryRouter()  # 🎯 모드 라우터 초기화

        # 🧠 LLM 의도 분류기 연결 (2025-12-23)
        if hasattr(self.generator, "llm"):
            self.query_router.set_llm(self.generator.llm)  # type: ignore[attr-defined]

        # 📦 Phase 3 서비스 (2026-01-04)
        self.cache_service = CacheService()
        self.conversation_service = ConversationService()

        # 📄 문서 처리 유틸리티 (분리된 모듈)
        self._doc_utils = DocumentUtils(
            retriever=self.retriever,
            extracted_dir=settings.EXTRACTED_DIR,
        )

        # 🔒 Closed-World Validation: 고유 기안자 캐싱
        self.known_drafters = RAGPipelineFactory.load_known_drafters()

        # 🎯 Handler 초기화 (Strangler Fig 패턴)
        from app.rag.handlers import CostSumHandler, DocumentHandler, SearchHandler
        from app.rag.handlers.comprehensive_report import ComprehensiveReportHandler
        self._search_handler = SearchHandler(self)
        self._document_handler = DocumentHandler(self)
        self._cost_sum_handler = CostSumHandler(self)
        self._comprehensive_report_handler = ComprehensiveReportHandler(self)  # 2025-12-26

        # 📊 유사 문서 추천 서비스 (2025-12-08)
        self._similarity_service = DocumentSimilarity(retriever=self.retriever)

        # 🎯 v2.0: 분리된 컴포넌트 초기화
        self._mode_resolver: ModeResolver = get_mode_resolver()
        self._response_builder: ResponseBuilder = get_response_builder()

        logger.info(f"RAG Pipeline v2.0 initialized (known_drafters: {len(self.known_drafters)}명)")

    def _load_full_text_if_short(self, filename: str, snippet: str) -> str:
        """스니펫이 짧으면 data/extracted에서 전체 텍스트 로드 (DocumentUtils 위임)"""
        return self._doc_utils.load_full_text_if_short(filename, snippet)

    # ========================================================================
    # query() 헬퍼 메서드 (Phase 3 리팩터링)
    # ========================================================================

    def _normalize_current_question(self, query: str) -> str:
        """'현재 질문:' 접두사 제거 및 UI 메타데이터 정제

        Args:
            query: 원본 쿼리

        Returns:
            정제된 쿼리
        """
        actual_query = query
        if "현재 질문:" in query:
            parts = query.split("현재 질문:")
            if len(parts) > 1:
                actual_query = parts[-1].strip()
        return clean_ui_metadata(actual_query)

    def _check_cache(
        self,
        cache_key: str,
        route_mode: str,
        actual_query: str
    ) -> Optional[dict[str, Any]]:
        """2-tier 캐시 확인 (CacheService 위임)

        Args:
            cache_key: 캐시 키
            route_mode: 라우팅 모드
            actual_query: 정제된 쿼리

        Returns:
            캐시된 결과 또는 None
        """
        return self.cache_service.get(cache_key, route_mode, actual_query)

    def _handle_selected_document(
        self,
        actual_query: str,
        selected_filename: str,
        cache_key: str
    ) -> dict[str, Any]:
        """선택된 문서 즉시 처리 (검색·라우팅 스킵)

        조기 단락(early return) 패턴으로 성능 향상.
        검색·라우팅·압축 단계 완전 생략 → 20~60% 지연시간 감소

        Args:
            actual_query: 정제된 쿼리
            selected_filename: 선택된 파일명
            cache_key: 캐시 키

        Returns:
            DOCUMENT 모드 응답 딕셔너리
        """
        logger.info(f"⚡ 선택된 문서({selected_filename}) 감지 → 즉시 DOCUMENT 모드 실행 (검색 스킵)")

        # 파일명 정규화 (NFKC, 공백 정규화)
        import unicodedata
        normalized_filename = unicodedata.normalize("NFKC", selected_filename).strip()
        normalized_filename = re.sub(r"\s+", " ", normalized_filename)

        # 문서 답변 생성
        result = self._answer_document(actual_query, selected_filename=normalized_filename)

        # 2-tier 캐시 저장
        self.cache_service.set(cache_key, result)

        return result

    def _extract_document_reference(self, actual_query: str) -> Optional[str]:
        """쿼리에서 문서 참조 추출 (DB 검색)

        패턴: "문서제목 이 문서/해당 문서 ..."
        예: "2025-01-09_광화문_스튜디오 이 문서에 대해 설명해줘"

        Args:
            actual_query: 정제된 쿼리

        Returns:
            매칭된 파일명 또는 None
        """
        # 문서 참조 패턴 매칭
        doc_ref_pattern = r"^(.+?)\s+(이\s?문서|해당\s?문서|이문서)"
        match = re.match(doc_ref_pattern, actual_query, re.IGNORECASE)
        if not match:
            return None

        # 후보 제목 추출 및 날짜 패턴 제거
        candidate_title = match.group(1).strip()
        candidate_title = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]", "", candidate_title)

        # metadata_db에서 제목으로 문서 검색
        from app.data.metadata_db import MetadataDB
        db = MetadataDB()

        try:
            # 제목 정규화 (특수문자, 공백 처리)
            normalized_title = candidate_title.replace("_", " ").replace("&", "").strip()

            # DB에서 제목 유사도 검색 (LIKE 패턴)
            conn = db._get_conn()
            cursor = conn.cursor()
            query_sql = """
                SELECT filename, title FROM documents
                WHERE title LIKE ? OR filename LIKE ?
                ORDER BY
                    CASE
                        WHEN title = ? THEN 1
                        WHEN title LIKE ? THEN 2
                        ELSE 3
                    END
                LIMIT 1
            """
            like_pattern = f"%{normalized_title}%"
            cursor.execute(query_sql, (like_pattern, like_pattern, candidate_title, f"{candidate_title}%"))
            result = cursor.fetchone()

            if result:
                selected_filename = result[0]
                logger.info(f"📌 쿼리에서 문서명 추출: '{candidate_title}' → '{selected_filename}'")
                return selected_filename

        except sqlite3.OperationalError as e:
            logger.debug(f"문서명 추출 중 DB 일시 오류 (무시): {e}")
        except sqlite3.Error as e:
            logger.warning(f"⚠️ 문서명 추출 중 DB 오류 (무시): {e}")

        return None

    def _route_to_handler(
        self,
        actual_query: str,
        route_decision: RouteDecision,
        selected_filename: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """모드별 전문 핸들러 라우팅

        각 QueryMode에 맞는 핸들러로 요청을 위임.
        QA 모드는 None을 반환하여 표준 파이프라인으로 폴백.

        Args:
            actual_query: 정제된 쿼리
            route_decision: 라우팅 결정
            selected_filename: 선택된 파일명 (optional)

        Returns:
            핸들러 응답 또는 None (QA 모드 - 표준 파이프라인으로 폴백)
        """
        try:
            from app.api.notify import notify as _notify  # type: ignore[import-not-found]
        except ImportError:
            # notify 모듈이 없는 경우 no-op 함수 사용
            def _notify(*_args, **_kwargs):  # type: ignore[misc]
                pass

        mode = route_decision.mode

        logger.info(f"🔀 라우팅 결과: mode={mode.value}, reason={route_decision.reason}")

        # 💰 COST 모드: 비용 합계 직접 조회
        if mode == QueryMode.COST:
            _notify("search", "비용 데이터 조회 중...")
            _notify("generate", "합계 계산 중...")
            result = self._answer_cost_sum(actual_query)
            _notify("complete", "완료")
            return result

        # 📄 DOCUMENT 모드: 문서 내용/요약
        if mode == QueryMode.DOCUMENT:
            _notify("search", "문서 로드 중...")
            _notify("generate", "AI 답변 생성 중...")
            result = self._answer_document(actual_query, selected_filename=selected_filename)
            _notify("complete", "완료")
            return result

        # 🔍 SEARCH 모드: 문서 검색
        if mode == QueryMode.SEARCH:
            _notify("search", "문서 검색 중...")
            result = self._answer_search(actual_query)
            _notify("complete", "완료")
            return result

        # 🎯 SEARCH_CONTENT_ONLY 모드: 정밀 내용 검색
        if mode == QueryMode.SEARCH_CONTENT_ONLY:
            _notify("search", "정밀 검색 중...")
            result = self._answer_search_content_only(actual_query)
            _notify("complete", "완료")
            return result

        # 📊 YEAR_SUMMARY 모드: 연도별 다중 문서 요약
        if mode == QueryMode.YEAR_SUMMARY:
            _notify("search", f"{route_decision.year}년 문서 검색 중...")
            _notify("generate", "요약 생성 중...")
            result = self._answer_year_summary(actual_query, route_decision.year, route_decision.drafter)
            _notify("complete", "완료")
            return result

        # 📊 COMPREHENSIVE_REPORT 모드: 종합 리포트 생성
        if mode == QueryMode.COMPREHENSIVE_REPORT:
            _notify("search", "관련 문서 검색 중...")
            _notify("generate", "종합 리포트 생성 중...")
            result = self._comprehensive_report_handler.handle(actual_query)
            _notify("complete", "완료")
            return result

        # QA 모드는 None 반환 → 표준 파이프라인으로 폴백
        return None

    def _run_standard_pipeline(
        self,
        actual_query: str,
        enhanced_query: str,
        top_k: Optional[int],
        selected_filename: Optional[str],
        route_decision: Optional[RouteDecision],
        cache_key: str,
        table_request_detected: bool
    ) -> dict[str, Any]:
        """표준 RAG 파이프라인 실행 (검색 → 압축 → 생성)

        QA 모드 및 표준 처리 경로에서 사용.

        Args:
            actual_query: 정제된 쿼리
            enhanced_query: 향상된 쿼리 (표 요청 프롬프트 포함)
            top_k: 검색 결과 개수
            selected_filename: 선택된 파일명
            route_decision: 라우팅 결정
            cache_key: 캐시 키
            table_request_detected: 표 정리 요청 여부

        Returns:
            RAG 파이프라인 응답 딕셔너리
        """
        try:
            from app.api.notify import notify as _notify  # type: ignore[import-not-found]
        except ImportError:
            # notify 모듈이 없는 경우 no-op 함수 사용
            def _notify(*_args, **_kwargs):  # type: ignore[misc]
                pass

        logger.info(f"🔍 Pattern matching 대상 쿼리: '{actual_query[:100]}'")

        # 📊 표 정리 요청 처리
        if table_request_detected:
            logger.info("📊 표 정리 요청 감지: top_k 확대 (5 → 20), 프롬프트 강화")

        # RAG 파이프라인 실행
        _notify("search", "관련 문서 검색 중...")
        _notify("generate", "AI 답변 생성 중...")
        response: RAGResponse = self.query(
            enhanced_query,
            top_k=top_k or PipelineConfig.PIPELINE_TOP_K,
            selected_filename=selected_filename
        )
        _notify("complete", "완료")

        if not response.success:
            # 실패 시 빈 응답 반환
            return {
                "text": response.answer or "검색 결과가 없습니다.",
                "citations": [],
                "evidence": [],
                "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
            }

        # Evidence 구성
        evidence = [
            {
                "doc_id": c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": c.get("snippet", ""),
                "meta": c.get("meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}),
            }
            for c in (response.evidence_chunks or [])
        ]

        # Evidence 폴백 (검색 결과는 있지만 evidence가 없는 경우)
        evidence_injected = False
        if not evidence and response.raw_results:
            logger.info("Evidence empty, using raw_results[:3] as fallback")
            evidence = [
                {
                    "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                    "page": 0,
                    "snippet": r.get("snippet") or r.get("text_preview", "")[:PipelineConfig.SNIPPET_PREVIEW_LENGTH],
                    "meta": {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "filename": r.get("filename", ""),
                        "page": 0,
                    },
                }
                for r in response.raw_results[:PipelineConfig.EVIDENCE_FALLBACK_COUNT]
            ]
            evidence_injected = True

        # 진단 정보 추가
        if DIAG_RAG and response.diagnostics:
            response.diagnostics["evidence_count"] = len(evidence)
            response.diagnostics["evidence_injected"] = evidence_injected

        # 상태 구성
        status = {
            "retrieved_count": len(response.raw_results or []),
            "selected_count": len(evidence),
            "found": len(evidence) > 0,
        }

        # 성능 메트릭 로깅
        author_mode = bool(re.search(r"(작성자|기안자|제안자)", actual_query))
        search_ms = int(response.metrics.get("search_time", 0) * 1000)
        generate_ms = int(response.metrics.get("generate_time", 0) * 1000)
        total_ms = int(response.latency * 1000)

        logger.info(
            f'[RAG] query="{actual_query[:50]}..." | '
            f"retrieved={status['retrieved_count']} | "
            f"selected={status['selected_count']} | "
            f"found={status['found']} | "
            f"author_mode={author_mode} | "
            f"search={search_ms}ms | gen={generate_ms}ms | total={total_ms}ms"
        )

        # 결과 구성
        result = {
            "text": response.answer,
            "citations": evidence,
            "evidence": evidence,
            "status": status,
            "diagnostics": response.diagnostics if DIAG_RAG else None,
            "similar_documents": response.similar_documents,
        }

        # 캐싱
        self.cache_service.set(cache_key, result)

        return result

    def _validate_query_input(self, query: str) -> Optional[RAGResponse]:
        """입력 검증 - 빈 쿼리면 에러 응답 반환

        Args:
            query: 사용자 질문

        Returns:
            RAGResponse if invalid, None if valid
        """
        if not query or not query.strip():
            return RAGResponse(
                answer="",
                success=False,
                error="빈 질문입니다",
            )
        return None

    def query(
        self,
        query: str,
        top_k: int = PipelineConfig.PIPELINE_TOP_K,
        compression_ratio: float = PipelineConfig.DEFAULT_COMPRESSION_RATIO,
        _use_hyde: bool = False,  # Reserved for future HyDE implementation
        temperature: float = 0.1,
        selected_filename: Optional[str] = None,
    ) -> RAGResponse:
        """RAG 질의 v2.0 (단일 진입점)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수
            compression_ratio: 압축 비율
            _use_hyde: HyDE 사용 여부 (미구현, 향후 지원 예정)
            temperature: LLM 생성 온도
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

        Returns:
            RAGResponse: 답변 + 메타데이터
        """
        # 입력 검증
        if not query or not query.strip():
            return RAGResponse(answer="", success=False, error="빈 질문입니다")

        start_time = time.perf_counter()
        metrics: dict[str, Any] = {}
        diagnostics: dict[str, Any] = {}

        try:
            # 1. 검색
            phase1_start = time.perf_counter()
            results, metrics = self._perform_retrieval(
                query, top_k, selected_filename, diagnostics
            )
            phase1_time = time.perf_counter() - phase1_start
            logger.info(f"⏱️ Phase 1 (검색): {phase1_time:.2f}s")

            # 검색 결과 없음 → CHAT 모드로 폴백
            if not results:
                return self._handle_no_results(query, start_time, metrics, diagnostics)

            # 2. 압축
            phase2_start = time.perf_counter()
            compressed, metrics = self._perform_compression(
                results, compression_ratio, metrics, diagnostics
            )
            phase2_time = time.perf_counter() - phase2_start
            logger.info(f"⏱️ Phase 2 (압축): {phase2_time:.2f}s")

            # 3. 모드 결정 (ModeResolver 활용)
            phase3_start = time.perf_counter()
            mode_decision = self._mode_resolver.resolve(query, results)
            metrics.update(mode_decision.metrics)
            metrics["mode"] = mode_decision.mode
            determined_mode = mode_decision.mode
            phase3_time = time.perf_counter() - phase3_start
            logger.info(f"⏱️ Phase 3 (모드 결정): {phase3_time:.2f}s")

            # 4. 컨텍스트 수화 및 생성
            phase4_start = time.perf_counter()
            answer, metrics = self._hydrate_and_generate(
                query, compressed, determined_mode, temperature, metrics, diagnostics
            )
            phase4_time = time.perf_counter() - phase4_start
            logger.info(f"⏱️ Phase 4 (생성): {phase4_time:.2f}s")

            # 5. 응답 구성 (ResponseBuilder 활용)
            return self._response_builder.build_rag_response(
                query=query,
                answer=answer,
                results=results,
                compressed=compressed,
                determined_mode=determined_mode,
                start_time=start_time,
                metrics=metrics,
                diagnostics=diagnostics,
            )

        except SearchError as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return RAGResponse(
                answer="", success=False,
                error=f"[E_RETRIEVE] 검색 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except ModelError as e:
            logger.error(f"Model inference failed: {e}", exc_info=True)
            return RAGResponse(
                answer="", success=False,
                error=f"[E_GENERATE] 생성 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return RAGResponse(
                answer="", success=False,
                error=f"[E_UNKNOWN] {e!s}",
                latency=time.perf_counter() - start_time,
            )

    def _perform_retrieval(
        self,
        query: str,
        top_k: int,
        selected_filename: Optional[str],
        diagnostics: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """검색 수행

        Returns:
            (검색 결과, 메트릭)
        """
        metrics: dict[str, Any] = {}

        # pre-routing: 장비 질의 감지
        preliminary_mode = self._detect_preliminary_mode(query)

        # 검색 실행
        search_start = time.perf_counter()
        results = self.retriever.search(
            query, top_k, mode=preliminary_mode, selected_filename=selected_filename
        )
        metrics["search_time"] = time.perf_counter() - search_start

        # 검색 결과 진단 로그
        self._log_retrieval_results(results, preliminary_mode)

        if DIAG_RAG:
            diagnostics["retrieved_k"] = len(results)
            if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

        return results, metrics

    def _detect_preliminary_mode(self, query: str) -> str:
        """검색 전 모드 감지 (DOC_ANCHORED 필터링용)"""
        if hasattr(self, "query_router"):
            has_device = (
                getattr(self.query_router, "has_device_terms", None) or
                getattr(self.query_router, "_has_device_terms", None)
            )
            if callable(has_device) and has_device(query):
                logger.info("🎯 검색 전 DOC_ANCHORED 모드 감지 (장비 용어)")
                return "doc_anchored"
        return "chat"

    def _log_retrieval_results(
        self, results: list[dict[str, Any]], mode: str
    ) -> None:
        """검색 결과 Top-N 진단 로그"""
        logger.info(f"RETRIEVE_TOPN mode={mode}")
        for i, doc in enumerate(results[:PipelineConfig.LOG_TOP_RESULTS_COUNT], 1):
            score = doc.get("score", 0.0)
            doc_id = doc.get("doc_id", "unknown")
            snippet_preview = doc.get("snippet", "")[:PipelineConfig.LOG_SNIPPET_PREVIEW_LEN].replace("\n", " ")
            logger.info(f"  #{i} score={score:.4f} doc={doc_id} preview={snippet_preview}...")

    def _handle_no_results(
        self,
        query: str,
        start_time: float,
        metrics: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> RAGResponse:
        """검색 결과 없음 처리"""
        logger.warning(f"No results found for query: {query[:50]}")
        if DIAG_RAG:
            diagnostics["mode"] = "no_results"
            diagnostics["generate_path"] = "fallback_no_context"

        metrics["mode"] = "chat"
        metrics["top_score"] = 0.0

        return RAGResponse(
            answer="관련 문서가 검색되지 않았다.",
            success=True,
            latency=time.perf_counter() - start_time,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    def _perform_compression(
        self,
        results: list[dict[str, Any]],
        compression_ratio: float,
        metrics: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """압축 수행"""
        compress_start = time.perf_counter()
        compressed = self.compressor.compress(results, compression_ratio)
        metrics["compress_time"] = time.perf_counter() - compress_start

        # Generator에 청크 주입 (런타임 속성, 프로토콜 외부)
        if hasattr(self.generator, "compressed_chunks"):
            self.generator.compressed_chunks = compressed  # type: ignore[attr-defined]

        if DIAG_RAG:
            diagnostics["after_compress_k"] = len(compressed)
            diagnostics["compression_ratio"] = compression_ratio
            if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                logger.info(f"[DIAG] 압축 완료: {len(results)} → {len(compressed)}개 문서")

        return compressed, metrics

    def _hydrate_and_generate(
        self,
        query: str,
        compressed: list[dict[str, Any]],
        determined_mode: str,
        temperature: float,
        metrics: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """컨텍스트 수화 및 LLM 생성

        Returns:
            (생성된 답변, 업데이트된 메트릭)
        """
        # Context Hydrator (폴백 보장)
        try:
            from app.rag.utils.context_hydrator import hydrate_context
        except ImportError as e:
            logger.warning(f"⚠️ hydrate_context import 실패, 폴백 사용: {e}")
            hydrate_context = self._fallback_hydrate_context

        logger.info(f"🎯 모드={determined_mode} → 컨텍스트 최적화 시작")
        hydrate_start = time.perf_counter()
        context, hydrator_metrics = hydrate_context(
            compressed, max_len=PipelineConfig.CONTEXT_MAX_LENGTH, mode=determined_mode
        )
        metrics["hydrate_time"] = time.perf_counter() - hydrate_start
        metrics.update({f"ctx_{k}": v for k, v in hydrator_metrics.items()})

        # LLM 생성
        logger.info(f"🎯 모드={determined_mode} → 생성 시작")
        llm_gen_start = time.perf_counter()
        answer = self.generator.generate(query, context, temperature, mode=determined_mode)
        metrics["generate_time"] = time.perf_counter() - llm_gen_start

        if DIAG_RAG:
            diagnostics["mode"] = "normal"
            diagnostics["generate_path"] = "from_context"
            diagnostics["used_k"] = len(compressed)
            if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                logger.info(f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용")

        return answer, metrics

    @staticmethod
    def _fallback_hydrate_context(
        chunks: list[dict[str, Any]],
        max_len: int = 10000,
        mode: str = "rag",
    ) -> tuple[str, dict[str, Any]]:
        """안전 폴백: 청크 스니펫 결합"""
        parts = []
        for c in chunks:
            t = c.get("snippet") or c.get("content") or c.get("text") or ""
            if t:
                parts.append(t[:PipelineConfig.FALLBACK_SNIPPET_LENGTH])
        ctx = "\n\n".join(parts)[:max_len]
        return ctx, {"fallback": True, "joined": len(parts)}

    def _make_response(
        self, text: str, selected: list[dict[str, Any]], retrieved: list[dict[str, Any]],
    ) -> dict:
        """표준 응답 구조 생성 (citations 포함)

        Args:
            text: 생성된 답변 텍스트
            selected: 실제 사용된 청크 리스트 (압축 후)
            retrieved: 검색된 원본 결과 리스트

        Returns:
            표준화된 응답 dict (citations 필수)
        """
        citations = []
        for c in selected:
            filename = c.get("filename") or c.get("doc_id") or c.get("title", "")
            ref = _encode_file_ref(filename) if filename else None

            citations.append({
                "doc_id": c.get("doc_id"),
                "filename": filename,
                "title": c.get("title") or filename or c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": (
                    c.get("text") or c.get("snippet") or c.get("content") or ""
                )[:PipelineConfig.SNIPPET_PREVIEW_LENGTH],
                "ref": ref,  # 🔴 base64 인코딩된 파일 경로
                "preview_url": c.get("preview_url"),
                "download_url": c.get("download_url"),
            })

        return {
            "text": text,
            "citations": citations,  # 🔴 표준 키 (필수)
            "evidence": citations,  # 하위 호환성 (동일 데이터)
            "status": {
                "retrieved_count": len(retrieved),
                "selected_count": len(selected),
                "found": len(selected) > 0,  # 🔴 유일한 판정 기준
            },
        }

    def answer(
        self,
        query: str,
        /,
        top_k: Optional[int] = None,
        selected_filename: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """답변 생성 (Evidence 포함 구조화된 응답)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수 (None이면 기본값 5)
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)
            **kwargs: 추가 옵션 (RAGProtocol 호환용)

        Returns:
            dict: {
                "text": 답변 텍스트,
                "citations": 참고 문서 목록 (표준 키),
                "evidence": 참고 문서 목록 (하위 호환),
                "status": {
                    "retrieved_count": int,
                    "selected_count": int,
                    "found": bool
                }
            }
        """
        # kwargs에서 top_k, selected_filename 추출 (호환성)
        top_k = kwargs.get("top_k", top_k)
        selected_filename = kwargs.get("selected_filename", selected_filename)

        # 진행 상태 로깅 헬퍼 (터미널 확인용)
        def _notify(step: str, message: str) -> None:
            logger.info(f"[{step.upper()}] {message}")

        # 대화 로깅 헬퍼 (2025-12-26 수정: actual_query 사용)
        import time
        start_time = time.time()

        def _log_and_return(result: dict[str, Any], mode: str, actual_query: str) -> dict[str, Any]:
            """결과 반환 전 대화 로깅 (ConversationService 위임)

            Args:
                result: 응답 딕셔너리
                mode: 처리 모드
                actual_query: 정제된 쿼리

            Returns:
                로깅 완료된 result 딕셔너리
            """
            self.conversation_service.log_answer(
                result=result,
                mode=mode,
                query=actual_query,
                start_time=start_time,
                client_ip=kwargs.get("client_ip"),
                session_id=kwargs.get("session_id"),
            )
            return result

        # 2025-12-26: Phase 2-3 - 쿼리 정제를 최상단에서 먼저 수행 (라우팅/캐시 키 통일)
        # 2026-01-02: Phase 1.1 - 정규화 로직 헬퍼로 추출 (DRY 원칙)
        actual_query = self._normalize_current_question(query)

        # 🎯 조기 라우팅: 정제된 쿼리로 모드 결정
        # 2025-12-23: 동일 쿼리라도 모드에 따라 다른 결과가 나올 수 있음
        # 예: "2025년 문서" → search 모드 vs year_summary 모드
        _notify("routing", "쿼리 분석 중...")
        early_route = self.query_router.classify_mode(actual_query)  # query → actual_query
        route_mode = early_route.mode.value
        _notify("routing", f"모드 결정: {route_mode}")

        # 📊 2025-12-26: 표 정리 요청 감지 (캐시 키 구분 위해 조기 감지)
        # "표로 알려줘", "표로 보여줘", "표로 정리해줘" 등
        table_request_detected = bool(
            re.search(r"표(로|를)?", actual_query) and
            any(kw in actual_query for kw in ["다", "전부", "모두", "전체", "모든", "알려", "보여", "정리"])
        )

        # ✨ 2-tier Cache check - 메모리 캐시 → 영구 캐시 (정제된 쿼리로 키 생성)
        # 표 정리 요청은 다른 형식의 답변이므로 별도 캐시 키 사용
        cache_suffix = "_table" if table_request_detected else ""
        cache_key = build_answer_cache_key(actual_query, selected_filename, mode=route_mode) + cache_suffix

        # Phase 2.1: 캐시 확인 로직을 헬퍼로 추출
        cached_result = self._check_cache(cache_key, route_mode, actual_query)
        if cached_result:
            return _log_and_return(cached_result, route_mode, actual_query)

        # Phase 2.2: 선택된 문서 조기 처리 로직을 헬퍼로 추출
        if selected_filename:
            result = self._handle_selected_document(actual_query, selected_filename, cache_key)
            return _log_and_return(result, "document", actual_query)

        # 🔥 CRITICAL: 기안자/날짜 검색은 QuickFixRAG에 위임 (전문 로직 보유)
        if hasattr(self.generator, "rag"):
            # Phase 2.3: 쿼리에서 문서 참조 추출 로직을 헬퍼로 추출
            if not selected_filename:
                selected_filename = self._extract_document_reference(actual_query)

            # 🎯 모드 라우팅: 조기 라우팅 결과 재사용 (이미 actual_query로 수행됨, Phase 2-3)
            route_decision = early_route
            logger.debug("🔄 조기 라우팅 결과 재사용 (actual_query 통일)")

            # 🔧 selected_filename이 있으면 무조건 DOCUMENT 모드로 전환 (우선순위 최상위)
            # 문서가 선택된 상태에서는 모든 질문에 대해 LLM이 해당 문서 기반으로 답변
            if selected_filename:
                logger.info(f"🎯 선택된 문서({selected_filename}) 감지 → DOCUMENT 모드로 강제")
                route_decision.mode = QueryMode.DOCUMENT
                route_decision.reason = "selected_doc"

            # 🔧 요약 의도 + 쿼리에 날짜/문서명 패턴이 있으면 DOCUMENT 모드로 강제
            has_summary_intent = self.query_router.SUMMARY_INTENT_PATTERN.search(actual_query) or "내용" in actual_query.lower()
            has_date_pattern = re.search(r"\d{4}[-_]\d{2}[-_]\d{2}", actual_query)  # 2025-06-10 형식

            if has_summary_intent and has_date_pattern and not selected_filename:
                logger.info("🎯 요약 의도 + 날짜 패턴 감지 → DOCUMENT 모드로 강제")
                route_decision.mode = QueryMode.DOCUMENT
                route_decision.reason = "summary_with_date_pattern"

            # Phase 2.4: 모드별 핸들러 라우팅 로직을 헬퍼로 추출
            handler_result = self._route_to_handler(actual_query, route_decision, selected_filename)
            if handler_result:
                return _log_and_return(handler_result, route_decision.mode.value, actual_query)

            # Phase 2.5: 표준 RAG 파이프라인 로직을 헬퍼로 추출
            # 📊 표 정리 요청 시 쿼리 향상
            enhanced_query = actual_query
            if table_request_detected:
                top_k = 20  # 검색 범위 확대
                enhanced_query = f"""{actual_query}

[중요 지시사항]
- 검색된 모든 문서의 정보를 빠짐없이 표에 포함할 것
- 각 문서당 1개 행 (요약/생략 금지)
- 표 컬럼: 날짜 | 문서명 | 주요내용 | 상태/결과
- 원본 데이터 그대로 사용 (LLM이 재작성/추론 금지)
- 표 아래에 '총 N개 문서' 명시"""

            result = self._run_standard_pipeline(
                actual_query,
                enhanced_query,
                top_k,
                selected_filename,
                route_decision,
                cache_key,
                table_request_detected
            )
            return _log_and_return(result, route_decision.mode.value if route_decision else "qa", actual_query)

        # hasattr(self.generator, "rag")가 False인 경우의 폴백
        # actual_query는 이미 상단에서 정제됨 (Phase 2-3, Line 507-513)
        response = self.query(actual_query, top_k=top_k or PipelineConfig.PIPELINE_TOP_K, selected_filename=selected_filename)

        if response.success:
            evidence = [
                {
                    "doc_id": c.get("doc_id"),
                    "page": c.get("page", 1),
                    "snippet": c.get("snippet", ""),
                    "meta": c.get(
                        "meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)},
                    ),
                }
                for c in (response.evidence_chunks or [])
            ]

            evidence_injected = False
            if not evidence and response.raw_results:
                logger.info("Evidence empty, using raw_results[:3] as fallback")
                evidence = [
                    {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "page": 0,
                        "snippet": r.get("snippet") or r.get("text_preview", "")[:PipelineConfig.SNIPPET_PREVIEW_LENGTH],
                        "meta": {
                            "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                            "filename": r.get("filename", ""),
                            "page": 0,
                        },
                    }
                    for r in response.raw_results[:PipelineConfig.EVIDENCE_FALLBACK_COUNT]
                ]
                evidence_injected = True

            if DIAG_RAG and response.diagnostics:
                response.diagnostics["evidence_count"] = len(evidence)
                response.diagnostics["evidence_injected"] = evidence_injected

            status = {
                "retrieved_count": len(response.raw_results or []),
                "selected_count": len(evidence),
                "found": len(evidence) > 0,
            }

            author_mode = bool(re.search(r"(작성자|기안자|제안자)", actual_query))
            search_ms = int(response.metrics.get("search_time", 0) * 1000)
            generate_ms = int(response.metrics.get("generate_time", 0) * 1000)
            total_ms = int(response.latency * 1000)

            logger.info(
                f'[RAG] query="{actual_query[:50]}..." | '
                f"retrieved={status['retrieved_count']} | "
                f"selected={status['selected_count']} | "
                f"found={status['found']} | "
                f"author_mode={author_mode} | "
                f"search={search_ms}ms | gen={generate_ms}ms | total={total_ms}ms",
            )

            result = {
                "text": response.answer,
                "citations": evidence,
                "evidence": evidence,
                "similar_documents": [],
                "status": status,
                "diagnostics": response.diagnostics if DIAG_RAG else {},
            }

            self.cache_service.set(cache_key, result)

            return _log_and_return(result, "qa", actual_query)

        error_msg = ERROR_MESSAGES.get(
            ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다.",
        )
        if response.error:
            error_msg = f"{error_msg}\n\n상세: {response.error}"

        logger.error(
            f'[RAG] query="{actual_query[:50]}..." | '
            f'status=ERROR | error="{response.error}"',
        )

        error_result = {
            "text": error_msg,
            "citations": [],
            "evidence": [],
            "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
        }
        return _log_and_return(error_result, "error", actual_query)

    def answer_text(self, query: str) -> str:
        """답변 텍스트만 반환 (하위 호환성)

        Args:
            query: 사용자 질문

        Returns:
            str: 생성된 답변 텍스트
        """
        result = self.answer(query)
        return result["text"]

    def _answer_search(self, query: str) -> dict:
        """문서 검색 - SearchHandler로 위임 (Strangler Fig 패턴)"""
        return self._search_handler.handle(query)

    def _answer_search_content_only(self, query: str) -> dict:
        """정밀 내용 검색 - SearchHandler로 위임 (Strangler Fig 패턴)"""
        return self._search_handler.handle(query, content_only=True)

    def _answer_cost_sum(self, query: str) -> dict:
        """비용 합계 조회 - CostSumHandler로 위임 (Strangler Fig 패턴)"""
        return self._cost_sum_handler.handle(query)

    def _answer_year_summary(
        self,
        query: str,
        year: Optional[int] = None,
        drafter: Optional[str] = None,
    ) -> dict:
        """연도별 다중 문서 요약 (2025-12-23 추가)

        지정된 연도의 모든 문서를 조회하여 LLM이 종합 요약을 생성합니다.

        Args:
            query: 사용자 질의
            year: 대상 연도 (None이면 쿼리에서 추출)
            drafter: 기안자 필터 (None이면 전체)

        Returns:
            dict: 답변 및 증거 포함
        """
        import sqlite3
        from datetime import datetime

        # 쿼리에서 기안자 추출 (RouteDecision에서 전달되지 않은 경우)
        if not drafter:
            drafter_match = re.search(r"([가-힣]{2,4})\s*(문서|기안서|작성|기안)", query)
            if drafter_match:
                drafter = drafter_match.group(1)

        logger.info(f"📊 YEAR_SUMMARY 모드 실행: year={year}, drafter={drafter}, query={query[:50]}...")

        # 연도 확정
        if not year:
            # 쿼리에서 연도 추출
            year_match = re.search(r"(\d{4})", query)
            if year_match:
                year = int(year_match.group(1))
            else:
                year = datetime.now().year  # 기본값: 올해

        # metadata.db에서 해당 연도 문서 조회
        try:
            from app.config.settings import settings
            db_path = getattr(settings, "METADATA_DB_PATH", None) or "metadata.db"

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # drafter 필터 조건 동적 생성
            if drafter:
                cursor.execute("""
                    SELECT id, filename, title, date, drafter, doctype, claimed_total, text_preview
                    FROM documents
                    WHERE year = ? AND drafter = ?
                    ORDER BY date DESC
                """, (str(year), drafter))
            else:
                cursor.execute("""
                    SELECT id, filename, title, date, drafter, doctype, claimed_total, text_preview
                    FROM documents
                    WHERE year = ?
                    ORDER BY date DESC
                """, (str(year),))

            rows = cursor.fetchall()
            conn.close()

            doc_count = len(rows)
            drafter_info = f" (기안자: {drafter})" if drafter else ""
            logger.info(f"📄 {year}년{drafter_info} 문서 {doc_count}개 조회됨")

            if doc_count == 0:
                no_doc_msg = f"{year}년에 {drafter}님이 작성한 문서가 없습니다." if drafter else f"{year}년에 등록된 문서가 없습니다."
                return {
                    "text": no_doc_msg,
                    "citations": [],
                    "evidence": [],
                    "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
                }

            # 문서 분류 (doctype별)
            categories = {}
            for row in rows:
                doctype = row["doctype"] or "기타"
                if doctype not in categories:
                    categories[doctype] = []
                categories[doctype].append(dict(row))

            # LLM에 전달할 컨텍스트 생성 (요약용)
            # 2025-12-26: 컨텍스트 과다 방지 - 상위 카테고리만 표시
            MAX_CATEGORIES_DISPLAY = 5  # 상위 5개 카테고리만
            DOCS_PER_CATEGORY = 5       # 각 카테고리당 5개 문서만

            header = f"## {year}년 {drafter}님 문서 현황 (총 {doc_count}개)\n" if drafter else f"## {year}년 문서 현황 (총 {doc_count}개)\n"
            context_parts = [header]

            # 상위 카테고리만 선택 (문서 수 기준 내림차순)
            top_categories = sorted(categories.items(), key=lambda x: -len(x[1]))[:MAX_CATEGORIES_DISPLAY]

            for doctype, docs in top_categories:
                context_parts.append(f"\n### {doctype} ({len(docs)}건)")
                for doc in docs[:DOCS_PER_CATEGORY]:  # 각 카테고리당 제한
                    # 2025-12-26: filename 필드 추가 (팩트 추적/검증 강화)
                    filename_display = doc["filename"]
                    title = doc["title"] or filename_display
                    date = doc["date"] or "날짜 없음"
                    doc_drafter = doc["drafter"] or "기안자 없음"
                    amount = doc["claimed_total"]
                    amount_str = f" | amount={amount:,}원" if amount else ""
                    # 구조화된 형식으로 변경 (LLM이 임의 변경 방지)
                    context_parts.append(
                        f"- date={date} | doctype={doctype} | title={title[:50]} | "
                        f"filename={filename_display} | drafter={doc_drafter}{amount_str}"
                    )

            context = "\n".join(context_parts)

            # 안전장치: 비정상적으로 긴 컨텍스트 제한 (버그 방어)
            MAX_CONTEXT_CHARS = 10000
            if len(context) > MAX_CONTEXT_CHARS:
                logger.warning(f"⚠️ YEAR_SUMMARY 컨텍스트 과다 ({len(context)}자 → {MAX_CONTEXT_CHARS}자 제한)")
                context = context[:MAX_CONTEXT_CHARS] + "\n... (이하 생략)"

            # LLM으로 요약 생성 (지시문과 컨텍스트 분리)
            # 2025-12-26: 중복 삽입 제거 - prompt에는 지시문만, context는 파라미터로
            subject = f"{year}년 {drafter}님" if drafter else f"{year}년"
            prompt = (
                f"{subject} 문서 {doc_count}개를 정리하라.\n\n"
                "[지시사항]\n"
                "- 아래 컨텍스트의 팩트(date/title/doctype/drafter/claimed_total/filename)를 변경하지 말 것\n"
                "- 카테고리별로 현황을 요약하되, 날짜/금액/파일명은 그대로 인용할 것\n"
                "- 문서에 없는 정보를 추측하지 말 것"
            )

            # 2025-12-26: Phase 2-1 - DB 집계 + LLM 요약 분리 (정확성 강화)
            # 1부: DB 집계 결과 (코드가 직접 생성, 팩트 보장)
            summary_header = f"## {year}년 문서 현황\n"
            summary_header += f"총 **{doc_count}개** 문서\n\n"
            summary_header += "### 카테고리별 분포\n"
            # 2025-12-26: 전체 categories 표시 (top 5 → all categories)
            all_categories_sorted = sorted(categories.items(), key=lambda x: -len(x[1]))
            for doctype, docs in all_categories_sorted:
                summary_header += f"- {doctype}: {len(docs)}건\n"

            # 2부: LLM 요약 (설명 역할만, context는 파라미터로만 전달)
            try:
                llm_explanation = self.generator.generate(
                    query=prompt,           # 지시문만
                    context=context,        # 팩트 데이터
                    temperature=0.2,        # 일관성 강화 (0.3 → 0.2)
                    mode="year_summary",    # 1024 토큰 예산 (constants.py에서 조정)
                )
            except Exception as e:
                logger.error(f"LLM 호출 실패: {e}")
                # 폴백: DB 집계만 사용 (LLM 없이도 동작)
                llm_explanation = "상세 내역은 위 카테고리를 참고하세요."

            # 최종 응답: 1부(팩트) + 2부(설명)
            answer = f"{summary_header}\n### 상세 내역\n{llm_explanation}"

            # Evidence 생성 (상위 문서들)
            evidence = [
                {
                    "doc_id": row["filename"],
                    "page": 0,
                    "snippet": (row["text_preview"] or "")[:200],
                    "meta": {
                        "doc_id": row["filename"],
                        "filename": row["filename"],
                        "title": row["title"],
                        "date": row["date"],
                        "drafter": row["drafter"],
                    },
                }
                for row in rows[:5]  # 상위 5개만
            ]

            return {
                "text": answer,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": doc_count,
                    "selected_count": min(doc_count, 5),
                    "found": True,
                    "year": year,
                },
            }

        except Exception as e:
            logger.error(f"YEAR_SUMMARY 처리 실패: {e}", exc_info=True)
            return {
                "text": f"연도별 요약 처리 중 오류가 발생했습니다: {e}",
                "citations": [],
                "evidence": [],
                "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
            }

    def _answer_document(self, query: str, selected_filename: Optional[str] = None) -> dict:
        """문서 내용 조회 - DocumentHandler로 위임 (Strangler Fig 패턴)"""
        return self._document_handler.handle(query, selected_filename=selected_filename)

    def _safe_fname(
        self, meta: Optional[dict[str, Any]] = None, doc_path: Optional[str] = None
    ) -> str:
        """파일명 안전 추출 (DocumentUtils 위임)"""
        return self._doc_utils.safe_fname(meta or {}, doc_path or "")

    def _make_chunks_for_doc(self, filename: str) -> list:
        """특정 문서의 청크만 로드 (DocumentUtils 위임)"""
        return self._doc_utils.make_chunks_for_doc(filename)

    def _extract_with_ocr(self, pdf_path: str, start_page: int, total_pages: int) -> str:
        """OCR을 사용하여 PDF에서 텍스트 추출 (DocumentUtils 위임)"""
        return self._doc_utils.extract_with_ocr(pdf_path, start_page, total_pages)

    def _gather_summary_context(self, filename: str, pdf_path: str, doc_locked: bool = False) -> str:
        """요약용 컨텍스트 수집 (DocumentUtils 위임)"""
        return self._doc_utils.gather_summary_context(filename, pdf_path, doc_locked)

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
    # 내부 헬퍼: 기본 구현 생성 (RAGPipelineFactory 위임)
    # ========================================================================

    def _create_default_retriever(self) -> Retriever:
        """기본 검색 엔진 생성 (RAGPipelineFactory 위임)"""
        return RAGPipelineFactory.create_retriever()

    def _create_default_compressor(self) -> Compressor:
        """기본 압축기 생성 (RAGPipelineFactory 위임)"""
        return RAGPipelineFactory.create_compressor()

    def _create_default_generator(self) -> Generator:
        """기본 LLM 생성기 생성 (RAGPipelineFactory 위임)"""
        return RAGPipelineFactory.create_generator()

    def _create_legacy_adapter(self) -> Optional["_LLMAdapter"]:
        """레거시 구현 어댑터 생성 (RAGPipelineFactory 위임)"""
        return RAGPipelineFactory.create_legacy_adapter()

    def _load_known_drafters(self) -> set:
        """메타DB에서 고유 기안자 로드 (RAGPipelineFactory 위임)"""
        return RAGPipelineFactory.load_known_drafters()
