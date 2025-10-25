"""하이브리드 검색 래퍼 (1단계: 기존 구현 활용)

기존 rag_system/hybrid_search.HybridSearch를 래핑하여
새로운 인터페이스로 통합합니다.

Example:
    >>> retriever = HybridRetriever()
    >>> results = retriever.search("질문")
    >>> print(results[0]["doc_id"], results[0]["score"])
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional

from app.core.logging import get_logger
from app.core.errors import SearchError, ErrorCode

logger = get_logger(__name__)


# ============================================================================
# Legacy 구현 import (선택적)
# ============================================================================

_LegacyHybrid = None

try:
    from rag_system.hybrid_search import HybridSearch as _LegacyHybrid

    logger.info("Legacy HybridSearch import 성공")
except Exception as e:
    logger.warning(f"Legacy HybridSearch import 실패: {e}")
    _LegacyHybrid = None


# ============================================================================
# HybridRetriever (래퍼)
# ============================================================================

class HybridRetriever:
    """하이브리드 검색 엔진 (BM25 + Dense)

    현재는 기존 rag_system/hybrid_search.HybridSearch를 래핑합니다.
    향후 내부 구현을 이 클래스로 점진적으로 이관합니다.

    Example:
        >>> retriever = HybridRetriever()
        >>> retriever.warmup()
        >>> results = retriever.search("2023년 구매 내역")
        >>> for r in results:
        ...     print(f"{r['doc_id']} (score: {r['score']:.3f})")
    """

    def __init__(
        self,
        vector_weight: float = None,
        bm25_weight: float = None,
        use_reranker: bool = False,  # CRITICAL: 다단계 필터링 비활성화
        use_query_expansion: bool = False,  # CRITICAL: 쿼리 확장 비활성화
        use_document_compression: bool = False,  # CRITICAL: 문서 압축 비활성화
        **kwargs: Any,
    ):
        """하이브리드 검색 엔진 초기화

        Args:
            vector_weight: 벡터 검색 가중치 (기본 0.2)
            bm25_weight: BM25 검색 가중치 (기본 0.8)
            use_reranker: 재랭킹 사용 여부 (기본 True)
            use_query_expansion: 쿼리 확장 사용 여부 (기본 True)
            use_document_compression: 문서 압축 사용 여부 (기본 True)
            **kwargs: 추가 파라미터
        """
        # Load weights from .env if not provided
        import os
        if vector_weight is None:
            vector_weight = float(os.getenv('SEARCH_VECTOR_WEIGHT', '0.01'))
        if bm25_weight is None:
            bm25_weight = float(os.getenv('SEARCH_BM25_WEIGHT', '0.99'))

        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.use_reranker = use_reranker
        self.use_query_expansion = use_query_expansion
        self.use_document_compression = use_document_compression

        # 🔥 MetadataDB 초기화 (snippet fallback용)
        self.db = self._lazy_db()

        # Legacy 구현 초기화
        if _LegacyHybrid:
            try:
                self._impl = _LegacyHybrid(
                    vector_weight=vector_weight,
                    bm25_weight=bm25_weight,
                    use_reranker=use_reranker,
                    use_query_expansion=use_query_expansion,
                    use_document_compression=use_document_compression,
                    **kwargs,
                )
                logger.info("HybridRetriever 초기화 완료 (Legacy 구현 사용)")
            except Exception as e:
                logger.error(f"Legacy HybridSearch 초기화 실패: {e}")
                self._impl = None
        else:
            self._impl = None
            logger.warning("Legacy HybridSearch 없음, 폴백 모드")

    def _lazy_db(self):
        """🔥 MetadataDB lazy 초기화 (snippet fallback용)"""
        try:
            from app.data.metadata.db import MetadataDB
            return MetadataDB()
        except Exception as e:
            logger.warning(f"MetadataDB 초기화 실패 (snippet fallback 비활성화): {e}")
            return None

    def _env_int(self, key: str, default: int) -> int:
        """환경변수를 int로 파싱"""
        import os
        try:
            return int(os.getenv(key, str(default)))
        except:
            return default

    def _fallback_snippet(self, item: Dict[str, Any]) -> str:
        """🔥 snippet 결손 보강 (빈 경우 DB에서 추출)

        Args:
            item: 검색 결과 dict

        Returns:
            str: snippet (최대 500자)
        """
        SNIPPET_MINLEN = self._env_int("SNIPPET_MINLEN", 200)  # 🔥 200자로 상향

        # 1) 제공된 snippet
        s = (item.get("snippet") or "").strip()
        if s and len(s) >= SNIPPET_MINLEN:
            return s

        # 2) content 필드
        c = (item.get("content") or "").strip()
        if c and len(c) >= SNIPPET_MINLEN:
            return c[: max(SNIPPET_MINLEN, 500)]

        # 3) DB/스토어 조회 (페이지 우선 → 문서 전체)
        text = None
        if self.db:
            try:
                doc_id = item.get("doc_id") or item.get("chunk_id")
                if not doc_id:
                    return "(내용 없음)"

                # 페이지 단위 조회 우선 시도
                page = item.get("page")
                get_page = getattr(self.db, "get_page_text", None)
                if callable(get_page) and page is not None:
                    text = get_page(doc_id, page)

                # 페이지 조회 실패 시 문서 전체 조회
                if not text:
                    get_doc = getattr(self.db, "get_content", None)
                    if callable(get_doc):
                        text = get_doc(doc_id)

            except Exception as e:
                logger.debug(f"DB snippet 조회 실패: {e}")

        text = (text or "").strip()
        return text[: max(SNIPPET_MINLEN, 500)] if text else "(내용 없음)"

    def warmup(self) -> None:
        """워밍업: 인덱스 사전 로드

        첫 검색 지연을 제거하기 위해 시작 시 호출.
        """
        if self._impl and hasattr(self._impl, "warmup"):
            try:
                self._impl.warmup()
                logger.info("HybridRetriever warmup 완료")
            except Exception as e:
                logger.warning(f"Warmup 실패: {e}")
        else:
            logger.info("HybridRetriever warmup (no-op)")

    def _backfill_results(
        self,
        query: str,
        got: List[Dict[str, Any]],
        need: int,
    ) -> List[Dict[str, Any]]:
        """🔥 최소 개수(need)를 못 채운 경우, 완화 검색으로 추가 채움

        Args:
            query: 검색 질의
            got: 기존 검색 결과
            need: 필요한 최소 개수

        Returns:
            보강된 검색 결과
        """
        if len(got) >= need:
            return got

        logger.info(f"Backfill: {len(got)}개 → 최소 {need}개 확보 시도")
        extras = []

        # 1) BM25-only 완화 검색
        if len(got) < need and self._impl:
            try:
                bm25_results = self._impl.bm25_store.search(query, top_k=need * 2)
                for r in bm25_results:
                    r['backfill_source'] = 'bm25'
                extras.extend(bm25_results)
                logger.debug(f"Backfill BM25: {len(bm25_results)}개 추가")
            except Exception as e:
                logger.debug(f"Backfill BM25 실패: {e}")

        # 2) Vector-only 완화 검색
        if len(got) < need and self._impl:
            try:
                vec_results = self._impl.vector_store.search(query, top_k=need * 2)
                for r in vec_results:
                    r['backfill_source'] = 'vector'
                extras.extend(vec_results)
                logger.debug(f"Backfill Vector: {len(vec_results)}개 추가")
            except Exception as e:
                logger.debug(f"Backfill Vector 실패: {e}")

        # 중복 제거 (doc_id, page 조합 기준)
        def key(x):
            return (x.get("doc_id", x.get("chunk_id", "")), x.get("page", 0))

        seen = set(key(r) for r in got)
        out = []

        for r in extras:
            k = key(r)
            if k not in seen and k[0]:  # doc_id가 있는 경우만
                seen.add(k)
                # snippet 보강
                item = {
                    "doc_id": r.get("doc_id", r.get("chunk_id", "unknown")),
                    "page": r.get("page", 1),
                    "score": r.get("score", 0.0),
                    "snippet": r.get("snippet", r.get("content", "")[:200]),
                    "meta": r.get("meta", {}),
                    "backfill": True,
                    "backfill_source": r.get("backfill_source", "unknown"),
                }
                item["snippet"] = self._fallback_snippet(item)
                out.append(item)

                if len(got) + len(out) >= need:
                    break

        logger.info(f"Backfill 완료: {len(got)}개 + {len(out)}개 = {len(got) + len(out)}개")
        return got + out

    def search(
        self,
        query: str,
        top_k: int = 5,
        include_debug: bool = False,
    ) -> List[Dict[str, Any]]:
        """검색 수행

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            include_debug: 디버그 정보 포함 여부

        Returns:
            검색 결과 리스트. 각 결과는 다음 키를 포함:
            - doc_id: 문서 ID
            - page: 페이지 번호
            - score: 검색 점수
            - snippet: 스니펫
            - meta: 메타데이터 (doc_id, page, title 등)

        Raises:
            SearchError: 검색 실패 시
        """
        if not query or not query.strip():
            logger.warning("빈 검색 질의")
            return []

        # 🔥 환경변수에서 설정 읽기
        DEFAULT_TOP_K = self._env_int("DEFAULT_TOP_K", top_k)
        MIN_TOP_K = self._env_int("MIN_TOP_K", 3)

        try:
            if self._impl:
                # Legacy 구현 호출 (🔥 DEFAULT_TOP_K 사용)
                legacy_results = self._impl.search(
                    query=query,
                    top_k=DEFAULT_TOP_K,
                    include_debug=include_debug,
                )

                # 결과 정규화
                if isinstance(legacy_results, dict):
                    # {"results": [...]} 또는 {"fused_results": [...]} 형태
                    results = legacy_results.get("results") or legacy_results.get("fused_results", [])
                elif isinstance(legacy_results, list):
                    results = legacy_results
                else:
                    logger.warning(f"예상치 못한 결과 형태: {type(legacy_results)}")
                    results = []

                # 결과 정규화: 필수 키 보장
                normalized = []
                for r in results:
                    if not isinstance(r, dict):
                        continue

                    item = {
                        "doc_id": r.get("doc_id", r.get("chunk_id", "unknown")),
                        "page": r.get("page", 1),
                        "score": r.get("score", 0.0),
                        "snippet": r.get("snippet", r.get("content", "")[:200]),
                        "meta": r.get("meta", {
                            "doc_id": r.get("doc_id", "unknown"),
                            "page": r.get("page", 1),
                            "title": r.get("title", ""),
                        }),
                    }

                    # 🔥 snippet 보강 (비어있거나 짧으면 DB에서 가져오기)
                    item["snippet"] = self._fallback_snippet(item)

                    normalized.append(item)

                # 🔥 Backfill: MIN_TOP_K 미만이면 추가 검색
                if len(normalized) < MIN_TOP_K:
                    normalized = self._backfill_results(query, normalized, MIN_TOP_K)

                # 🔥 최종 상위 DEFAULT_TOP_K로 제한
                final = normalized[:DEFAULT_TOP_K]

                logger.info(f"검색 완료: {len(final)}개 결과 (요청={top_k}, 기본={DEFAULT_TOP_K}, 최소={MIN_TOP_K})")
                return final

            else:
                # 폴백: 빈 결과
                logger.warning("검색 엔진 없음, 빈 결과 반환")
                return []

        except Exception as e:
            logger.error(f"검색 실패: {e}", exc_info=True)
            raise SearchError(
                "검색 중 오류가 발생했습니다",
                details=str(e),
            ) from e

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """문서 추가 (인덱싱)

        Args:
            texts: 문서 텍스트 리스트
            metadatas: 메타데이터 리스트

        Raises:
            SearchError: 인덱싱 실패 시
        """
        if self._impl and hasattr(self._impl, "add_documents"):
            try:
                self._impl.add_documents(texts, metadatas)
                logger.info(f"{len(texts)}개 문서 인덱싱 완료")
            except Exception as e:
                logger.error(f"문서 추가 실패: {e}", exc_info=True)
                raise SearchError("문서 인덱싱 실패", details=str(e)) from e
        else:
            logger.warning("add_documents 미지원 (폴백 모드)")

    def save_indexes(self) -> None:
        """인덱스 저장

        Raises:
            SearchError: 저장 실패 시
        """
        if self._impl and hasattr(self._impl, "save_indexes"):
            try:
                self._impl.save_indexes()
                logger.info("인덱스 저장 완료")
            except Exception as e:
                logger.error(f"인덱스 저장 실패: {e}", exc_info=True)
                raise SearchError("인덱스 저장 실패", details=str(e)) from e
        else:
            logger.warning("save_indexes 미지원 (폴백 모드)")

    def get_stats(self) -> Dict[str, Any]:
        """검색 통계 반환

        Returns:
            통계 딕셔너리 (cache_hit_rate, total_searches 등)
        """
        if self._impl and hasattr(self._impl, "get_stats"):
            try:
                return self._impl.get_stats()
            except Exception as e:
                logger.warning(f"통계 조회 실패: {e}")

        return {
            "cache_hit_rate": 0.0,
            "total_searches": 0,
        }
