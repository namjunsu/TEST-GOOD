"""Dense Retrieval Stage v1.1

벡터 기반 의미론적 검색을 수행하는 Stage입니다.

특징:
- sentence-transformers 기반 임베딩
- FAISS 벡터 검색
- BM25와 RRF(Reciprocal Rank Fusion)로 결합

2025-12-21 v1.1 변경사항:
- 하드코딩된 값들을 HybridRetrieverConfig로 외부화
"""

import os
from typing import Any, Optional

from app.core.logging import get_logger
from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult
from config.constants import HybridRetrieverConfig

logger = get_logger(__name__)


class DenseStage(BaseSearchStage):
    """Dense Retrieval Stage

    벡터 임베딩 기반 의미론적 검색을 수행합니다.
    BM25 Stage와 함께 실행되어 RRF로 결합됩니다.

    Attributes:
        name: "DenseStage"
        priority: 2 (ExactMatch 다음, MetadataRouting 전)
    """

    name: str = "DenseStage"
    priority: int = 2  # ExactMatch(1) 다음

    def __init__(
        self,
        enabled: bool = True,
        min_score: float = 0.3,
    ):
        """초기화

        Args:
            enabled: 활성화 여부 (환경변수 ENABLE_DENSE_RETRIEVAL)
            min_score: 최소 유사도 점수 (이하 결과 필터링)
        """
        self.enabled = enabled and os.getenv(
            "ENABLE_DENSE_RETRIEVAL", "true"
        ).lower() == "true"
        self.min_score = min_score

        self._vector_store = None
        self._initialized = False

        if self.enabled:
            self._lazy_init()

    def _lazy_init(self):
        """Lazy 초기화 (벡터 스토어 로드)"""
        if self._initialized:
            return

        try:
            from app.rag.embeddings import get_vector_store

            self._vector_store = get_vector_store()

            if self._vector_store.is_empty:
                logger.warning(
                    "⚠️ DenseStage: 벡터 인덱스가 비어있습니다. "
                    "인덱싱 스크립트를 실행해주세요."
                )
                self.enabled = False
            else:
                stats = self._vector_store.get_stats()
                logger.info(
                    f"✅ DenseStage 초기화 완료: "
                    f"{stats['total_vectors']}개 벡터, "
                    f"{stats['total_documents']}개 문서"
                )

            self._initialized = True

        except Exception as e:
            logger.error(f"❌ DenseStage 초기화 실패: {e}")
            self.enabled = False

    def should_skip(self, context: SearchContext) -> bool:
        """스킵 조건 체크

        - Dense Retrieval 비활성화
        - strict_content 모드 (정밀 검색은 BM25만 사용)
        - 특정 파일 선택됨 (selected_filename)
        """
        if not self.enabled:
            return True

        if context.strict_content:
            return True

        if context.selected_filename:
            return True

        return False

    def execute(self, context: SearchContext) -> StageResult:
        """Dense 검색 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult (should_continue=True, BM25와 결합용)
        """
        if not self.enabled or self._vector_store is None:
            return self._make_empty_result("Dense Retrieval 비활성화")

        try:
            # 벡터 검색
            results = self._vector_store.search(
                query=context.query,
                top_k=context.top_k * HybridRetrieverConfig.DENSE_TOPK_MULTIPLIER,
            )

            # 최소 점수 필터링
            filtered_results = [
                r for r in results
                if r.get("score", 0) >= self.min_score
            ]

            # 결과 정규화 (HybridRetriever 스키마에 맞춤)
            normalized = self._normalize_results(filtered_results)

            logger.info(
                f"🔍 DenseStage: {len(normalized)}건 검색 "
                f"(원본 {len(results)}건, 필터 후)"
            )

            return StageResult(
                normalized,  # results (positional)
                True,  # should_continue: BM25 결과와 결합
                self.name,  # stage_name
                len(normalized),  # hit_count
                {  # metadata
                    "raw_count": len(results),
                    "filtered_count": len(normalized),
                    "min_score": self.min_score,
                },
            )

        except Exception as e:
            logger.error(f"❌ DenseStage 실행 실패: {e}")
            return self._make_empty_result(f"에러: {e}")

    def _normalize_results(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """결과 정규화 (HybridRetriever 스키마)

        Args:
            results: VectorStore 검색 결과

        Returns:
            정규화된 결과 리스트
        """
        normalized = []

        for r in results:
            normalized.append({
                "filename": r.get("doc_id", ""),
                "doc_id": r.get("doc_id", ""),
                "snippet": r.get("snippet", r.get("text", "")[:HybridRetrieverConfig.DENSE_SNIPPET_MAX_LENGTH]),
                "score": r.get("score", 0.0),
                "page": r.get("metadata", {}).get("page", 1),
                "chunk_id": r.get("chunk_id", ""),
                "chunk_index": r.get("chunk_index", 0),
                "source": "dense",
                "meta": r.get("metadata", {}),
            })

        return normalized


class HybridRanker:
    """하이브리드 랭킹 (RRF)

    BM25와 Dense 결과를 RRF(Reciprocal Rank Fusion)로 결합합니다.

    Args:
        k: RRF 파라미터 (기본 60, 논문 권장)
        bm25_weight: BM25 가중치
        dense_weight: Dense 가중치
    """

    def __init__(
        self,
        k: int = HybridRetrieverConfig.RRF_K,
        bm25_weight: float = HybridRetrieverConfig.RRF_BM25_WEIGHT,
        dense_weight: float = HybridRetrieverConfig.RRF_DENSE_WEIGHT,
    ):
        self.k = k
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight

    def fuse(
        self,
        bm25_results: list[dict[str, Any]],
        dense_results: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """RRF로 결과 결합

        Args:
            bm25_results: BM25 검색 결과
            dense_results: Dense 검색 결과
            top_k: 상위 K개 반환

        Returns:
            결합된 결과 리스트 (score=RRF점수)
        """
        if not bm25_results and not dense_results:
            return []

        # 문서별 RRF 점수 계산
        doc_scores: dict[str, float] = {}
        doc_data: dict[str, dict] = {}

        # BM25 결과 처리
        for rank, result in enumerate(bm25_results):
            doc_id = result.get("filename") or result.get("doc_id", "")
            rrf_score = self.bm25_weight / (self.k + rank + 1)

            if doc_id not in doc_scores:
                doc_scores[doc_id] = 0.0
                doc_data[doc_id] = result.copy()
                doc_data[doc_id]["bm25_rank"] = rank + 1
                doc_data[doc_id]["bm25_score"] = result.get("score", 0.0)

            doc_scores[doc_id] += rrf_score

        # Dense 결과 처리
        for rank, result in enumerate(dense_results):
            doc_id = result.get("filename") or result.get("doc_id", "")
            rrf_score = self.dense_weight / (self.k + rank + 1)

            if doc_id not in doc_scores:
                doc_scores[doc_id] = 0.0
                doc_data[doc_id] = result.copy()

            doc_scores[doc_id] += rrf_score

            # Dense 정보 추가
            if doc_id in doc_data:
                doc_data[doc_id]["dense_rank"] = rank + 1
                doc_data[doc_id]["dense_score"] = result.get("score", 0.0)

        # 점수순 정렬
        sorted_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # 결과 구성
        results = []
        for doc_id, rrf_score in sorted_docs[:top_k]:
            data = doc_data[doc_id]
            data["score"] = rrf_score
            data["rrf_score"] = rrf_score
            data["source"] = "hybrid"
            results.append(data)

        logger.info(
            f"🔀 HybridRanker: BM25({len(bm25_results)}) + "
            f"Dense({len(dense_results)}) → {len(results)}건"
        )

        return results


# 싱글톤 인스턴스
_hybrid_ranker: Optional[HybridRanker] = None


def get_hybrid_ranker(
    bm25_weight: float = HybridRetrieverConfig.RRF_BM25_WEIGHT,
    dense_weight: float = HybridRetrieverConfig.RRF_DENSE_WEIGHT,
) -> HybridRanker:
    """HybridRanker 싱글톤 반환"""
    global _hybrid_ranker

    if _hybrid_ranker is None:
        _hybrid_ranker = HybridRanker(
            bm25_weight=bm25_weight,
            dense_weight=dense_weight,
        )

    return _hybrid_ranker
