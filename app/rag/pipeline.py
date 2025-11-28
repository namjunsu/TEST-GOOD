"""RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.errors import (
    ERROR_MESSAGES,
    ErrorCode,
    ModelError,
    SearchError,
)
from app.core.logging import get_logger
from app.rag.cache_manager import (
    build_answer_cache_key,
    cache_query_result,
    get_cached_result,
)
from app.rag.persistent_cache import cache_query_result_persistent, get_cached_result_persistent
from app.rag.query_router import QueryMode, QueryRouter
from app.config.settings import settings

# 분리된 모듈에서 import
from app.rag.contracts import (
    RAGResponse,
    Retriever,
    Compressor,
    Generator,
)
from app.rag.query_routing import (
    DIAG_RAG,
    DIAG_LOG_LEVEL,
    clean_ui_metadata,
    has_domain_keyword,
    get_keyword_coverage,
    force_chat_mode,
    _encode_file_ref,
)
from app.rag.utils.text import get_query_token_count
from app.rag.adapters import (
    _DummyRetriever,
    _NoOpCompressor,
    _DummyGenerator,
    _LLMAdapter,
    _QuickFixGenerator,
)

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
        self.retriever = retriever or self._create_default_retriever()
        self.compressor = compressor or self._create_default_compressor()
        self.generator = generator or self._create_default_generator()
        self.query_router = QueryRouter()  # 🎯 모드 라우터 초기화

        # 🔒 Closed-World Validation: 고유 기안자 캐싱
        self.known_drafters = self._load_known_drafters()

        # 🎯 Handler 초기화 (Strangler Fig 패턴)
        from app.rag.handlers import SearchHandler, DocumentHandler, CostSumHandler
        self._search_handler = SearchHandler(self)
        self._document_handler = DocumentHandler(self)
        self._cost_sum_handler = CostSumHandler(self)

        logger.info(f"RAG Pipeline initialized (known_drafters: {len(self.known_drafters)}명)")

    def _load_full_text_if_short(self, filename: str, snippet: str) -> str:
        """스니펫이 짧으면 data/extracted에서 전체 텍스트 로드"""
        # settings 중앙 설정 사용
        extracted_dir = settings.EXTRACTED_DIR
        min_snippet_len = settings.DOC_ANCHOR_MIN_SNIPPET

        if len(snippet) >= min_snippet_len:
            return snippet

        # 파일명에서 확장자 제거 후 .txt 찾기
        stem = os.path.splitext(filename)[0]
        txt_path = extracted_dir / f"{stem}.txt"

        if txt_path.exists():
            try:
                full_text = txt_path.read_text(encoding="utf-8", errors="ignore")
                logger.info(f"📄 DOC_ANCHORED: {filename} 전체 텍스트 로드 ({len(full_text)}자)")
                return full_text[:5000]  # 최대 5000자
            except Exception as e:
                logger.warning(f"⚠️ 전체 텍스트 로드 실패: {e}")

        return snippet

    # ========================================================================
    # query() 헬퍼 메서드 (Phase 3 리팩터링)
    # ========================================================================

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

    def _perform_retrieval(
        self,
        query: str,
        top_k: int,
        preliminary_mode: str,
        selected_filename: Optional[str],
        diagnostics: dict,
    ) -> tuple[List[Dict[str, Any]], dict]:
        """검색 수행

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수
            preliminary_mode: 검색 모드 ("chat", "doc_anchored")
            selected_filename: 선택된 문서 파일명
            diagnostics: 진단 정보 딕셔너리

        Returns:
            (검색 결과 리스트, 메트릭 딕셔너리)
        """
        metrics = {}
        search_start = time.perf_counter()
        results = self.retriever.search(
            query, top_k, mode=preliminary_mode, selected_filename=selected_filename
        )
        metrics["search_time"] = time.perf_counter() - search_start

        # [검색 결과 Top-N 진단 로그]
        logger.info(f"RETRIEVE_TOPN mode={preliminary_mode}")
        for i, doc in enumerate(results[:10], 1):
            score = doc.get("score", 0.0)
            doc_id = doc.get("doc_id", "unknown")
            snippet_preview = doc.get("snippet", "")[:60].replace("\n", " ")
            logger.info(f"  #{i} score={score:.4f} doc={doc_id} preview={snippet_preview}...")

        # [DIAG] 검색 결과 진단
        if DIAG_RAG:
            diagnostics["retrieved_k"] = len(results)
            if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

        return results, metrics

    def _determine_rag_mode(
        self,
        query: str,
        results: List[Dict[str, Any]],
        metrics: dict,
    ) -> str:
        """RAG 모드 결정 (chat/rag)

        Args:
            query: 사용자 질문
            results: 검색 결과
            metrics: 메트릭 딕셔너리 (업데이트됨)

        Returns:
            결정된 모드 ("chat" 또는 "rag")
        """
        mode_env = settings.MODE
        top_score = results[0].get("score", 0.0) if results else 0.0
        metrics["top_score"] = top_score

        if mode_env == "AUTO":
            # 1. 강제 CHAT 모드 체크 (스몰토크/산술/짧은 질의)
            should_force, force_reason = force_chat_mode(query)
            if should_force:
                metrics["mode"] = "chat"
                metrics["force_chat_reason"] = force_reason
                logger.info(f"🎯 AUTO 모드: CHAT 강제 적용 (이유: {force_reason})")
            else:
                # 2. 도메인 키워드 + 절대값 임계값 기반 판단
                has_keyword = has_domain_keyword(query)
                token_count = get_query_token_count(query)

                use_absolute = settings.RAG_MIN_SCORE_POLICY == "absolute"
                vec_min = settings.VEC_MIN_ABS

                if use_absolute:
                    pass_abs_threshold = top_score >= vec_min
                    pass_domain = has_keyword
                    pass_length = token_count >= 4

                    # Coverage Gate
                    keyword_coverage = get_keyword_coverage(query, results)
                    min_coverage = settings.MIN_KEYWORD_COVERAGE
                    pass_coverage = keyword_coverage >= min_coverage

                    should_use_rag = (
                        pass_abs_threshold and pass_domain and pass_length and pass_coverage
                    )
                    metrics["mode"] = "rag" if should_use_rag else "chat"
                    metrics["keyword_coverage"] = keyword_coverage

                    logger.info(
                        f"🎯 AUTO 모드 (절대값): top_score={top_score:.3f}, "
                        f"has_keyword={has_keyword}, token_count={token_count}, "
                        f"coverage={keyword_coverage}/{min_coverage}, "
                        f"threshold={vec_min}, selected_mode={metrics['mode']}"
                    )
                else:
                    # 기존 정규화 정책 (fallback)
                    rag_min_score = settings.RAG_MIN_SCORE
                    metrics["mode"] = "rag" if top_score >= rag_min_score else "chat"
                    logger.info(
                        f"🎯 AUTO 모드 (정규화): top_score={top_score:.3f}, "
                        f"threshold={rag_min_score}, selected_mode={metrics['mode']}"
                    )
        elif mode_env == "CHAT":
            metrics["mode"] = "chat"
            metrics["top_score"] = 0.0
        else:  # RAG, SUMMARIZE
            metrics["mode"] = "rag"
            metrics["top_score"] = results[0].get("score", 0.0) if results else 0.0

        return metrics.get("mode", "rag")

    def _hydrate_and_generate(
        self,
        query: str,
        compressed: List[Dict[str, Any]],
        determined_mode: str,
        temperature: float,
        metrics: dict,
        diagnostics: dict,
    ) -> str:
        """컨텍스트 수화 및 LLM 생성

        Args:
            query: 사용자 질문
            compressed: 압축된 청크 리스트
            determined_mode: 결정된 모드
            temperature: 생성 온도
            metrics: 메트릭 딕셔너리 (업데이트됨)
            diagnostics: 진단 정보 딕셔너리

        Returns:
            생성된 답변
        """
        # Context Hydrator with mode-aware optimization (폴백 보장)
        try:
            from app.rag.utils.context_hydrator import hydrate_context
        except Exception as e:
            logger.warning(f"⚠️ hydrate_context import 실패, 폴백 사용: {e}")

            def hydrate_context(
                chunks: List[Dict[str, Any]],
                max_len: int = 10000,
                mode: str = "rag"
            ) -> tuple[str, Dict[str, Any]]:
                """안전 폴백: 청크 스니펫 결합"""
                parts = []
                for c in chunks:
                    t = (c.get("snippet") or c.get("content") or c.get("text") or "")
                    if t:
                        parts.append(t[:800])
                ctx = "\n\n".join(parts)[:max_len]
                return ctx, {"fallback": True, "joined": len(parts)}

        hydrate_start = time.perf_counter()
        context, hydrator_metrics = hydrate_context(compressed, max_len=10000, mode=determined_mode)
        metrics["hydrate_time"] = time.perf_counter() - hydrate_start
        metrics.update({f"ctx_{k}": v for k, v in hydrator_metrics.items()})

        # LLM 생성
        logger.info(f"🎯 모드={determined_mode} → 생성 시작")
        llm_gen_start = time.perf_counter()
        answer = self.generator.generate(query, context, temperature, mode=determined_mode)
        metrics["generate_time"] = time.perf_counter() - llm_gen_start

        # [DIAG] 생성 완료 진단
        if DIAG_RAG:
            diagnostics["mode"] = "normal"
            diagnostics["generate_path"] = "from_context"
            diagnostics["used_k"] = len(compressed)
            if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                logger.info(
                    f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용"
                )

        return answer

    def _build_rag_response(
        self,
        query: str,
        answer: str,
        results: List[Dict[str, Any]],
        compressed: List[Dict[str, Any]],
        determined_mode: str,
        start_time: float,
        metrics: dict,
        diagnostics: dict,
    ) -> RAGResponse:
        """RAG 응답 구성

        Args:
            query: 사용자 질문
            answer: 생성된 답변
            results: 원본 검색 결과
            compressed: 압축된 결과
            determined_mode: 결정된 모드
            start_time: 시작 시간
            metrics: 메트릭
            diagnostics: 진단 정보

        Returns:
            RAGResponse 객체
        """
        total_latency = time.perf_counter() - start_time
        metrics["total_time"] = total_latency

        # 성능 가드: 슬로 쿼리 임계값 체크
        if total_latency > 10.0:
            logger.warning(
                f"⚠️  SLOW_QUERY (>10s): {total_latency:.2f}s | "
                f"query='{query[:50]}...' | "
                f"search={metrics['search_time']:.2f}s, "
                f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                f"generate={metrics['generate_time']:.2f}s"
            )
        elif total_latency > 3.0:
            logger.warning(
                f"⚠️  SLOW_QUERY (>3s): {total_latency:.2f}s | "
                f"query='{query[:50]}...'"
            )

        logger.info(
            f"RAG query completed in {total_latency:.2f}s "
            f"(search={metrics['search_time']:.2f}s, "
            f"compress={metrics['compress_time']:.2f}s, "
            f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
            f"generate={metrics['generate_time']:.2f}s)"
        )

        # CHAT 모드일 경우 출처 제거
        max_sources = 200 if any(
            kw in query.lower() for kw in ["전부", "모두", "모든", "전체", "all", "몇", "개수", "총"]
        ) else 3
        final_source_docs = (
            [] if determined_mode == "chat" else [c.get("doc_id") for c in results[:max_sources]]
        )
        final_evidence_chunks = [] if determined_mode == "chat" else compressed

        return RAGResponse(
            answer=answer,
            source_docs=final_source_docs,
            evidence_chunks=final_evidence_chunks,
            raw_results=results,
            latency=total_latency,
            success=True,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    def query(
        self,
        query: str,
        top_k: int = 5,
        compression_ratio: float = 0.7,
        _use_hyde: bool = False,  # Reserved for future HyDE implementation
        temperature: float = 0.1,
        selected_filename: Optional[str] = None,
    ) -> RAGResponse:
        """RAG 질의 (단일 진입점)

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
            return RAGResponse(
                answer="",
                success=False,
                error="빈 질문입니다",
            )

        start_time = time.perf_counter()
        metrics = {}
        diagnostics = {}  # 진단 정보 수집

        try:
            # 0. 검색 전 pre-routing: 장비 질의 감지 (DOC_ANCHORED 필터링용)
            # QueryRouter의 device term 감지 로직 활용 (공개 API 우선, fallback to 비공개)
            preliminary_mode = "chat"
            if hasattr(self, "query_router"):
                has_device = (
                    getattr(self.query_router, "has_device_terms", None) or
                    getattr(self.query_router, "_has_device_terms", None)
                )
                if callable(has_device) and has_device(query):
                    preliminary_mode = "doc_anchored"
                    logger.info("🎯 검색 전 DOC_ANCHORED 모드 감지 (장비 용어)")

            # 1. 검색: 정규화된 청크(dict) 리스트 기대
            search_start = time.perf_counter()
            results = self.retriever.search(query, top_k, mode=preliminary_mode, selected_filename=selected_filename)
            metrics["search_time"] = time.perf_counter() - search_start

            # [검색 결과 Top-N 진단 로그]
            logger.info(f"RETRIEVE_TOPN mode={preliminary_mode}")
            for i, doc in enumerate(results[:10], 1):
                score = doc.get("score", 0.0)
                doc_id = doc.get("doc_id", "unknown")
                snippet_preview = doc.get("snippet", "")[:60].replace("\n", " ")
                logger.info(f"  #{i} score={score:.4f} doc={doc_id} preview={snippet_preview}...")

            # [DIAG] 검색 결과 진단
            if DIAG_RAG:
                diagnostics["retrieved_k"] = len(results)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

            if not results:
                logger.warning(f"No results found for query: {query[:50]}")
                if DIAG_RAG:
                    diagnostics["mode"] = "no_results"
                    diagnostics["generate_path"] = "fallback_no_context"

                # 검색 결과 없음 → CHAT 모드로 폴백
                metrics["mode"] = "chat"
                metrics["top_score"] = 0.0

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
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 압축 완료: {len(results)} → {len(compressed)}개 문서"
                    )

            # 3. 생성: 모드 결정 → 컨텍스트 최적화 → 생성
            # CRITICAL: Inject compressed chunks into generator for proper LLM context
            if hasattr(self.generator, "compressed_chunks"):
                self.generator.compressed_chunks = compressed
                logger.debug(
                    f"Injected {len(compressed)} compressed chunks into generator"
                )

            # [DIAG] 생성 전 컨텍스트 스냅샷
            if DIAG_RAG and DIAG_LOG_LEVEL == "DEBUG":
                for i, c in enumerate(compressed[:3], 1):  # 상위 3개만 로그
                    logger.debug(
                        f"[DIAG] Context[{i}]: doc_id={c.get('doc_id')}, "
                        f"filename={c.get('filename', 'N/A')}, "
                        f"page={c.get('page', 0)}, "
                        f"snippet={c.get('snippet', '')[:120]}..."
                    )

            # 🎯 STEP 1: QueryRouter 모드 분류 (DOC_ANCHORED 최우선 체크)
            # CRITICAL: 검색 결과를 고려한 지능형 라우팅
            route_decision = self.query_router.classify_mode_with_retrieval(query, results)
            router_reason = route_decision.reason
            query_mode = route_decision.mode  # Extract QueryMode enum
            logger.info(f"🔀 QueryRouter 분류: mode={query_mode.value}, reason={router_reason}")

            # 🎯 STEP 2: 모드 결정 로직
            # CRITICAL: Determine mode BEFORE context hydration to apply mode-aware context limits
            mode_env = settings.MODE
            top_score = results[0].get("score", 0.0) if results else 0.0
            metrics["top_score"] = top_score

            if mode_env == "AUTO":
                # ━━━ 1. 강제 CHAT 모드 체크 (스몰토크/산술/짧은 질의) ━━━
                should_force, force_reason = force_chat_mode(query)
                if should_force:
                    metrics["mode"] = "chat"
                    metrics["force_chat_reason"] = force_reason
                    logger.info(f"🎯 AUTO 모드: CHAT 강제 적용 (이유: {force_reason})")
                else:
                    # ━━━ 2. 도메인 키워드 + 절대값 임계값 기반 판단 ━━━
                    has_keyword = has_domain_keyword(query)
                    token_count = get_query_token_count(query)

                    # settings 중앙 설정에서 절대값 임계값 읽기
                    use_absolute = settings.RAG_MIN_SCORE_POLICY == "absolute"
                    # bm25_min reserved for future BM25-specific scoring
                    vec_min = settings.VEC_MIN_ABS

                    # 절대값 정책 사용 시 (권장)
                    if use_absolute:
                        # 실제 BM25/벡터 스코어를 results에서 추출 시도
                        # (현재는 fused score만 있으므로 간소화)
                        # 일단 top_score를 벡터 스코어로 간주
                        pass_abs_threshold = top_score >= vec_min
                        pass_domain = has_keyword
                        pass_length = token_count >= 4

                        # 🔒 Coverage Gate: 검색 결과에서 실제로 키워드가 발견되는지 확인
                        keyword_coverage = get_keyword_coverage(query, results)
                        min_coverage = settings.MIN_KEYWORD_COVERAGE
                        pass_coverage = keyword_coverage >= min_coverage

                        should_use_rag = pass_abs_threshold and pass_domain and pass_length and pass_coverage
                        metrics["mode"] = "rag" if should_use_rag else "chat"
                        metrics["keyword_coverage"] = keyword_coverage

                        logger.info(
                            f"🎯 AUTO 모드 (절대값): top_score={top_score:.3f}, "
                            f"has_keyword={has_keyword}, token_count={token_count}, "
                            f"coverage={keyword_coverage}/{min_coverage}, "
                            f"threshold={vec_min}, selected_mode={metrics['mode']}"
                        )
                    else:
                        # 기존 정규화 정책 (fallback)
                        rag_min_score = settings.RAG_MIN_SCORE
                        metrics["mode"] = "rag" if top_score >= rag_min_score else "chat"
                        logger.info(
                            f"🎯 AUTO 모드 (정규화): top_score={top_score:.3f}, "
                            f"threshold={rag_min_score}, selected_mode={metrics['mode']}"
                        )

            elif mode_env == "CHAT":
                metrics["mode"] = "chat"
                metrics["top_score"] = 0.0
            else:  # RAG, SUMMARIZE
                metrics["mode"] = "rag"
                metrics["top_score"] = results[0].get("score", 0.0) if results else 0.0

            # 🎯 STEP 2: 모드 기반 컨텍스트 최적화
            determined_mode = metrics.get("mode", "rag")
            logger.info(f"🎯 모드={determined_mode} → 컨텍스트 최적화 시작")

            # Context Hydrator with mode-aware optimization (폴백 보장)
            try:
                from app.rag.utils.context_hydrator import hydrate_context
            except Exception as e:
                logger.warning(f"⚠️ hydrate_context import 실패, 폴백 사용: {e}")

                def hydrate_context(
                    chunks: List[Dict[str, Any]],
                    max_len: int = 10000,
                    mode: str = "rag"
                ) -> tuple[str, Dict[str, Any]]:
                    """안전 폴백: 청크 스니펫 결합"""
                    parts = []
                    for c in chunks:
                        t = (c.get("snippet") or c.get("content") or c.get("text") or "")
                        if t:
                            parts.append(t[:800])
                    ctx = "\n\n".join(parts)[:max_len]
                    return ctx, {"fallback": True, "joined": len(parts)}

            hydrate_start = time.perf_counter()
            context, hydrator_metrics = hydrate_context(compressed, max_len=10000, mode=determined_mode)
            metrics["hydrate_time"] = time.perf_counter() - hydrate_start
            # Merge hydrator metrics into main metrics
            metrics.update({f"ctx_{k}": v for k, v in hydrator_metrics.items()})

            # 🎯 STEP 3: 생성 (모드별 토큰 예산 적용)
            logger.info(f"🎯 모드={determined_mode} → 생성 시작")
            llm_gen_start = time.perf_counter()
            answer = self.generator.generate(query, context, temperature, mode=determined_mode)
            metrics["generate_time"] = time.perf_counter() - llm_gen_start

            # [DIAG] 생성 완료 진단
            if DIAG_RAG:
                diagnostics["mode"] = "normal"
                diagnostics["generate_path"] = "from_context"
                diagnostics["used_k"] = len(compressed)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용"
                    )

            total_latency = time.perf_counter() - start_time
            metrics["total_time"] = total_latency

            # 🚨 성능 가드: 슬로 쿼리 임계값 체크
            if total_latency > 10.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>10s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...' | "
                    f"search={metrics['search_time']:.2f}s, "
                    f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                    f"generate={metrics['generate_time']:.2f}s"
                )
            elif total_latency > 3.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>3s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...'"
                )

            logger.info(
                f"RAG query completed in {total_latency:.2f}s "
                f"(search={metrics['search_time']:.2f}s, "
                f"compress={metrics['compress_time']:.2f}s, "
                f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                f"generate={metrics['generate_time']:.2f}s)"
            )

            # CHAT 모드일 경우 출처 제거 (일반 대화는 문서 인용 불필요)
            # "전부" 또는 "개수" 질의 감지 시 출처도 더 많이 표시
            max_sources = 200 if any(kw in query.lower() for kw in ["전부", "모두", "모든", "전체", "all", "몇", "개수", "총"]) else 3
            final_source_docs = [] if determined_mode == "chat" else [c.get("doc_id") for c in results[:max_sources]]
            final_evidence_chunks = [] if determined_mode == "chat" else compressed

            return RAGResponse(
                answer=answer,
                source_docs=final_source_docs,
                evidence_chunks=final_evidence_chunks,  # UI용 근거
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

    def _make_response(
        self, text: str, selected: List[Dict[str, Any]], retrieved: List[Dict[str, Any]]
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
                )[:400],
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

    def answer(self, query: str, top_k: Optional[int] = None, selected_filename: Optional[str] = None) -> dict:
        """답변 생성 (Evidence 포함 구조화된 응답)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수 (None이면 기본값 5)
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

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
        # ✨ 2-tier Cache check - 메모리 캐시 → 영구 캐시
        cache_key = build_answer_cache_key(query, selected_filename)

        # Tier 1: 메모리 캐시 확인 (가장 빠름)
        cached_result = get_cached_result(cache_key)
        if cached_result:
            logger.info(f"🎯 Memory Cache HIT! Returning cached result for query: {query[:50]}...")
            if "status" in cached_result:
                cached_result["status"]["from_cache"] = "memory"
            return cached_result

        # Tier 2: 영구 캐시 확인 (서버 재시작 후에도 유지)
        cached_result = get_cached_result_persistent(cache_key)
        if cached_result:
            logger.info(f"💾 Persistent Cache HIT! Returning cached result for query: {query[:50]}...")
            # 영구 캐시에서 가져온 결과를 메모리 캐시에도 저장 (다음 접근을 위해)
            cache_query_result(cache_key, cached_result)
            if "status" in cached_result:
                cached_result["status"]["from_cache"] = "persistent"
            return cached_result

        # 🚀 조기 단락: 선택된 문서가 있으면 즉시 DOCUMENT 모드로 처리
        # 검색·라우팅·압축 단계 완전 생략 → 성능 향상 (20~60% 지연시간 감소)
        if selected_filename:
            logger.info(f"⚡ 선택된 문서({selected_filename}) 감지 → 즉시 DOCUMENT 모드 실행 (검색 스킵)")
            # 파일명 정규화 (NFKC, 공백 정규화, 대소문자 통일)
            import unicodedata
            normalized_filename = unicodedata.normalize("NFKC", selected_filename).strip()
            normalized_filename = re.sub(r"\s+", " ", normalized_filename)

            # UI 메타데이터 제거
            actual_query = clean_ui_metadata(query)

            # 확장 쿼리에서 실제 질문 추출
            if "현재 질문:" in actual_query:
                parts = actual_query.split("현재 질문:")
                if len(parts) > 1:
                    actual_query = parts[-1].strip()

            result = self._answer_document(actual_query, selected_filename=normalized_filename)

            # 결과 캐싱
            cache_query_result(cache_key, result)
            cache_query_result_persistent(cache_key, result)

            return result

        # 🔥 CRITICAL: 기안자/날짜 검색은 QuickFixRAG에 위임 (전문 로직 보유)
        if hasattr(self.generator, "rag"):
            # ✅ 확장된 쿼리에서 실제 질문 추출 (chat_interface.py 대응)
            actual_query = query
            if "현재 질문:" in query:
                parts = query.split("현재 질문:")
                if len(parts) > 1:
                    actual_query = parts[-1].strip()
                    logger.info(f"📝 확장 쿼리에서 추출: '{actual_query[:50]}'")

            # 🧹 UI 메타데이터 제거 (🏷 pdf · 📅 2024-10-24 · ✍ 등)
            actual_query = clean_ui_metadata(actual_query)

            # 🔍 쿼리에서 문서명 추출 (사용자가 직접 타이핑한 경우)
            # 패턴: "문서제목 이 문서/해당 문서 ..."
            if not selected_filename:
                doc_ref_pattern = r"^(.+?)\s+(이\s?문서|해당\s?문서|이문서)"
                match = re.match(doc_ref_pattern, actual_query, re.IGNORECASE)
                if match:
                    candidate_title = match.group(1).strip()
                    # 날짜 패턴 제거 (예: "2025-01-09_광화문_스튜디오..." → "광화문_스튜디오...")
                    candidate_title = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]", "", candidate_title)

                    # metadata_db에서 제목으로 문서 검색
                    from app.data.metadata_db import MetadataDB
                    db = MetadataDB()
                    try:
                        # 제목 정규화 (특수문자, 공백 처리)
                        normalized_title = candidate_title.replace("_", " ").replace("&", "").strip()

                        # DB에서 제목 유사도 검색 (LIKE 패턴)
                        conn = db.conn
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
                    except Exception as e:
                        logger.warning(f"문서명 추출 중 오류 (무시): {e}")

            # 🎯 모드 라우팅: Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모드 우선
            route_decision = self.query_router.classify_mode(actual_query)

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
                logger.info(f"🎯 요약 의도 + 날짜 패턴 감지 → DOCUMENT 모드로 강제")
                route_decision.mode = QueryMode.DOCUMENT
                route_decision.reason = "summary_with_date_pattern"

            logger.info(
                f"🔀 라우팅 결과: mode={route_decision.mode.value}, reason={route_decision.reason}"
            )

            # 💰 COST 모드: 비용 합계 직접 조회
            if route_decision.mode == QueryMode.COST:
                return self._answer_cost_sum(actual_query)

            # 📄 DOCUMENT 모드: 문서 내용/요약 (통합: PREVIEW + SUMMARY)
            if route_decision.mode == QueryMode.DOCUMENT:
                return self._answer_document(actual_query, selected_filename=selected_filename)

            # 🔍 SEARCH 모드: 문서 검색 (통합: LIST + SEARCH + LIST_FIRST)
            if route_decision.mode == QueryMode.SEARCH:
                return self._answer_search(actual_query)

            # 🎯 SEARCH_CONTENT_ONLY 모드: 정밀 내용 검색 (2025-11-19 추가)
            if route_decision.mode == QueryMode.SEARCH_CONTENT_ONLY:
                return self._answer_search_content_only(actual_query)

            # 🔍 디버깅: 실제 pattern matching 대상 로깅
            logger.info(f"🔍 Pattern matching 대상 쿼리: '{actual_query[:100]}'")

            # ✅ P0: 파일명 직접 언급 패턴 감지 (레거시 호환, PREVIEW 모드 외)
        # 일반 쿼리는 기존 로직 사용
        response = self.query(query, top_k=top_k or 5, selected_filename=selected_filename)

        if response.success:
            # 검색/압축에서 넘어온 정규화 청크 사용 (실제 page/snippet/meta 노출)
            evidence = [
                {
                    "doc_id": c.get("doc_id"),
                    "page": c.get("page", 1),
                    "snippet": c.get("snippet", ""),
                    "meta": c.get(
                        "meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}
                    ),
                }
                for c in (response.evidence_chunks or [])
            ]

            # CRITICAL: Evidence 최소 보장 (sources_cited가 비어도 검색 결과는 표시)
            evidence_injected = False
            if not evidence and response.raw_results:
                logger.info("Evidence empty, using raw_results[:3] as fallback")
                evidence = [
                    {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "page": 0,  # 검색 결과는 페이지 정보 없음
                        "snippet": r.get("snippet") or r.get("text_preview", "")[:400],  # 500 → 400 (스니펫 일관성)
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
                "found": len(evidence) > 0,  # 🔴 유일한 판정 기준
            }

            # 운영 표준 1행 요약 로그 (필수)
            author_mode = bool(re.search(r"(작성자|기안자|제안자)", query))
            search_ms = int(response.metrics.get("search_time", 0) * 1000)
            generate_ms = int(response.metrics.get("generate_time", 0) * 1000)
            total_ms = int(response.latency * 1000)

            logger.info(
                f'[RAG] query="{query[:50]}..." | '
                f"retrieved={status['retrieved_count']} | "
                f"selected={status['selected_count']} | "
                f"found={status['found']} | "
                f"author_mode={author_mode} | "
                f"backfill={evidence_injected} | "
                f"search_ms={search_ms} | "
                f"generate_ms={generate_ms} | "
                f"total_ms={total_ms}"
            )

            result = {
                "text": response.answer,
                "citations": evidence,  # 🔴 표준 키 (필수)
                "evidence": evidence,  # 하위 호환성 (동일 데이터)
                "status": status,  # UI에서 이것만 확인
                "diagnostics": response.diagnostics if DIAG_RAG else {},
            }

            # ✨ Cache the successful result to both tiers
            cache_key = build_answer_cache_key(query, selected_filename)
            cache_query_result(cache_key, result)  # Memory cache
            cache_query_result_persistent(cache_key, result)  # Persistent cache
            logger.info(f"📝 Cached result to memory + persistent storage for query: {query[:50]}...")

            return result
        else:
            # 에러 발생 시 (중립 톤, 사과 표현 금지)
            error_msg = ERROR_MESSAGES.get(
                ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다."
            )
            if response.error:
                error_msg = f"{error_msg}\n\n상세: {response.error}"

            # 운영 표준 로그 (에러 케이스)
            logger.error(
                f'[RAG] query="{query[:50]}..." | '
                f'status=ERROR | error="{response.error}"'
            )

            return {
                "text": error_msg,
                "citations": [],  # 🔴 표준 키 (필수)
                "evidence": [],  # 하위 호환성
                "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
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

    def _answer_search(self, query: str) -> dict:
        """문서 검색 - SearchHandler로 위임 (Strangler Fig 패턴)"""
        return self._search_handler.handle(query)

    def _answer_search_content_only(self, query: str) -> dict:
        """정밀 내용 검색 - SearchHandler로 위임 (Strangler Fig 패턴)"""
        return self._search_handler.handle(query, content_only=True)

    def _answer_cost_sum(self, query: str) -> dict:
        """비용 합계 조회 - CostSumHandler로 위임 (Strangler Fig 패턴)"""
        return self._cost_sum_handler.handle(query)

    def _answer_document(self, query: str, selected_filename: Optional[str] = None) -> dict:
        """문서 내용 조회 - DocumentHandler로 위임 (Strangler Fig 패턴)"""
        return self._document_handler.handle(query, selected_filename=selected_filename)

    def _safe_fname(self, meta: dict = None, doc_path: str = None) -> str:
        """파일명 안전 추출 (다양한 소스에서 시도)

        Args:
            meta: 메타데이터 딕셔너리
            doc_path: 문서 경로

        Returns:
            안전하게 추출된 파일명 (기본값: '미상 문서')
        """
        import os

        meta = meta or {}

        # 다양한 필드에서 파일명 시도
        fname = (
            meta.get("fname")
            or meta.get("filename")
            or meta.get("doc_id")
            or (os.path.basename(doc_path) if doc_path else None)
            or "미상 문서"
        )

        return fname

    def _make_chunks_for_doc(self, filename: str) -> list:
        """특정 문서의 청크만 로드 (문서 고정 모드용)

        Args:
            filename: 문서 파일명

        Returns:
            해당 문서의 청크 리스트
        """
        try:
            # BM25 인덱스에서 직접 해당 문서 찾기 (검색 대신 직접 접근)
            if hasattr(self.retriever, "bm25") and self.retriever.bm25:
                bm25_store = self.retriever.bm25

                # metadata에서 filename이 일치하는 문서의 인덱스 찾기
                target_indices = []
                for i, meta in enumerate(bm25_store.metadata):
                    if meta.get("filename") == filename:
                        target_indices.append(i)
                        logger.info(f"✅ BM25 인덱스에서 발견: {filename} (index={i})")

                # 찾은 문서들의 content를 청크로 변환
                chunks = []
                for idx in target_indices:
                    content = bm25_store.documents[idx]
                    if content and len(content.strip()) > 0:
                        # 전체 문서를 하나의 큰 청크로 사용
                        chunks.append({
                            "doc_id": filename,
                            "page": 1,
                            "text": content,  # 전체 텍스트
                            "score": 1.0,  # 직접 매칭이므로 최고 스코어
                            "filename": filename
                        })
                        logger.info(f"✓ 문서 content 로드: {len(content)}자")

                if chunks:
                    logger.info(f"✓ 문서 청크 {len(chunks)}개 로드 완료")
                    return chunks

            # BM25 사용 불가 시 폴백: 키워드 검색
            logger.warning("⚠️ BM25 직접 접근 불가, 검색으로 폴백")
            search_query = filename.replace(".pdf", "").replace("_", " ")
            results = self.retriever.search(search_query, top_k=20)

            # 검색 결과를 해당 문서로 필터링
            chunks = []
            for result in results:
                # doc_id 또는 meta.filename이 일치하는 경우만 포함
                doc_id = result.get("doc_id", "")
                meta_filename = result.get("meta", {}).get("filename", "")

                if filename in doc_id or filename in meta_filename:
                    chunks.append({
                        "doc_id": result.get("doc_id", filename),
                        "page": result.get("page", 1),
                        "text": result.get("snippet", result.get("text", "")),
                        "score": result.get("score", 0.0),
                        "filename": filename
                    })

            if not chunks:
                logger.warning(f"⚠️ 문서 청크 없음: {filename}")

            return chunks

        except Exception as e:
            logger.error(f"❌ 문서 청크 로드 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_with_ocr(self, pdf_path: str, start_page: int, total_pages: int) -> str:
        """OCR을 사용하여 PDF에서 텍스트 추출 (pytesseract 우선, paddleocr 폴백)

        Args:
            pdf_path: PDF 파일 경로
            start_page: 시작 페이지 (0-based)
            total_pages: 전체 페이지 수

        Returns:
            추출된 텍스트
        """
        try:
            import pytesseract
            from pdf2image import convert_from_path

            # PDF를 이미지로 변환 (끝 3페이지만)
            images = convert_from_path(
                pdf_path,
                first_page=start_page + 1,  # 1-based
                last_page=total_pages
            )

            text = ""
            for i, img in enumerate(images):
                try:
                    # pytesseract 사용
                    page_text = pytesseract.image_to_string(img, lang="kor+eng")
                    text += page_text + "\n"
                    logger.info(f"✓ OCR (pytesseract) 페이지 {start_page + i + 1}: {len(page_text)}자")
                except Exception as e:
                    logger.warning(f"⚠️ pytesseract 실패 (페이지 {start_page + i + 1}): {e}")

            if len(text.strip()) > 50:
                return text

            # pytesseract 실패 시 paddleocr 시도
            logger.info("🔄 paddleocr 폴백 시도...")
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang="korean")

                text = ""
                for i, img in enumerate(images):
                    # PaddleOCR는 파일 경로 또는 numpy array를 받음
                    import numpy as np
                    img_array = np.array(img)
                    result = ocr.ocr(img_array, cls=True)

                    if result and result[0]:
                        page_text = "\n".join([line[1][0] for line in result[0]])
                        text += page_text + "\n"
                        logger.info(f"✓ OCR (paddleocr) 페이지 {start_page + i + 1}: {len(page_text)}자")

                return text

            except Exception as e:
                logger.warning(f"⚠️ paddleocr 실패: {e}")
                return ""

        except Exception as e:
            logger.error(f"❌ OCR 추출 실패: {e}")
            return ""

    def _gather_summary_context(self, filename: str, pdf_path: str, doc_locked: bool = False) -> str:
        """요약용 컨텍스트 수집 (인덱스 청크 기반, PDF tail 비활성)

        Args:
            filename: 파일명
            pdf_path: PDF 파일 경로
            doc_locked: True면 해당 문서 청크만 사용 (다른 문서 검색 금지)

        Returns:
            수집된 컨텍스트 텍스트 (최대 ~3600자, 약 1.8k 토큰)
        """
        import re

        parts = []

        # 인덱스 청크 기반 컨텍스트 수집 (섹션 가중치 적용)
        # 우선순위 키워드: 개요, 배경, 검토사유, 대안, 견적, 결론, 비용, 도입사유
        priority_keywords = r"(개요|배경|검토사유|검토\s*사유|대안|견적|결론|비용|도입사유|도입\s*사유|구매목적|구매\s*목적|선정|권고|총액|합계)"

        try:
            if doc_locked:
                # 문서 고정 모드: 해당 문서의 청크만 로드
                logger.info(f"🔒 문서 고정 모드: {filename}의 청크만 사용")
                chunks = self._make_chunks_for_doc(filename)

                # 섹션 가중치 적용: 우선순위 키워드 포함 청크를 앞으로
                priority_chunks = []
                normal_chunks = []
                for chunk in chunks:
                    chunk_text = chunk.get("text") or chunk.get("snippet") or chunk.get("content") or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_chunks.append(chunk)
                    else:
                        normal_chunks.append(chunk)

                # 우선순위 청크 + 일반 청크 순서로 재조합, 최대 10개 (검토서 상세 정보 포함)
                sorted_chunks = (priority_chunks + normal_chunks)[:10]

                for i, chunk in enumerate(sorted_chunks, 1):
                    chunk_text = chunk.get("text") or chunk.get("snippet") or chunk.get("content") or ""
                    if chunk_text:
                        parts.append(f"=== [문서 청크 {i}] ===\n" + chunk_text[:5000])

                if sorted_chunks:
                    logger.info(f"✓ 문서 고정 청크 {len(sorted_chunks)}개 추출 (우선순위: {len(priority_chunks)}개)")
            else:
                # 일반 모드: 키워드 검색 후 같은 파일 필터링
                search_keywords = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", filename)  # 날짜 제거
                search_keywords = re.sub(r"\.pdf$", "", search_keywords, flags=re.IGNORECASE)
                search_keywords = search_keywords.replace("_", " ")

                hits = self.retriever.search(search_keywords, top_k=10)
                same_file_hits = [h for h in hits if h.get("filename") == filename]

                # 섹션 가중치 적용
                priority_hits = []
                normal_hits = []
                for h in same_file_hits:
                    chunk_text = h.get("text") or h.get("snippet") or h.get("content") or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_hits.append(h)
                    else:
                        normal_hits.append(h)

                sorted_hits = (priority_hits + normal_hits)[:10]

                for i, h in enumerate(sorted_hits, 1):
                    chunk_text = h.get("text") or h.get("snippet") or h.get("content") or ""
                    if chunk_text:
                        parts.append(f"=== [관련 청크 {i}] ===\n" + chunk_text[:5000])

                if sorted_hits:
                    logger.info(f"✓ RAG 청크 {len(sorted_hits)}개 추출 (우선순위: {len(priority_hits)}개)")
        except Exception as e:
            logger.warning(f"⚠️ RAG 청크 추출 실패: {e}")

        # 결합 및 길이 제한 (약 3k 토큰 ~ 6000자, 검토서 상세 정보 포함)
        context = "\n\n".join(parts)[:6000]
        logger.info(f"📋 최종 컨텍스트 길이: {len(context)}자 (청크 수: {len(parts)})")
        return context

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
        use_v2 = settings.USE_V2_RETRIEVER

        if use_v2:
            # V2 Retriever는 archive로 이동되었습니다 (20251026)
            # 레거시 코드를 제거하고 v1으로 폴백합니다
            logger.warning(
                "⚠️ USE_V2_RETRIEVER는 더 이상 지원되지 않습니다. v1 Retriever를 사용합니다."
            )
            use_v2 = False
            # try:
            #     from app.rag.retriever_v2 import HybridRetrieverV2
            #     v2_retriever = HybridRetrieverV2()
            #     logger.info("✅ HybridRetrieverV2 (v2 신규 시스템) 생성 완료")
            #
            #     # V2 adapter: fused_results → list 변환
            #     return _V2RetrieverAdapter(v2_retriever)
            # except Exception as e:
            #     logger.error(f"V2 Retriever 생성 실패, v1으로 폴백: {e}")
            #     # 폴백: v1 사용
            #     use_v2 = False

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

    def _create_legacy_adapter(self) -> Optional["_LLMAdapter"]:
        """레거시 구현 어댑터 생성 (캡슐화)

        QwenLLM을 래핑하여 기존 레거시 시스템과 연결합니다.
        향후 이 메서드만 수정하여 신규 구현으로 점진 전환 가능.

        Returns:
            _LLMAdapter: LLM 어댑터 인스턴스
        """
        try:
            from rag_system.active.llm_singleton import LLMSingleton

            model_path = settings.MODEL_PATH
            logger.info(f"🔍 DEBUG: Attempting to load LLM with model_path={model_path}")
            logger.info(f"🔍 DEBUG: Model file exists: {Path(model_path).exists()}")
            llm = LLMSingleton.get_instance(model_path=model_path)
            logger.info(f"✅ LLM adapter 생성 완료 (LLMSingleton 사용, model={model_path})")
            return _LLMAdapter(llm)
        except Exception as e:
            logger.error(f"LLM adapter 생성 실패: {e}", exc_info=True)
            return None

    def _load_known_drafters(self) -> set:
        """메타DB에서 고유 기안자 로드 (Closed-World Validation용)

        Returns:
            set: 고유 기안자 이름 집합
        """
        try:
            from app.data.metadata_db import MetadataDB

            db = MetadataDB()
            drafters = db.list_unique_drafters()
            db.close()

            logger.info(f"✅ 고유 기안자 {len(drafters)}명 캐싱 완료")
            return drafters
        except Exception as e:
            logger.error(f"기안자 로드 실패: {e}")
            return set()


