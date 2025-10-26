"""HybridRetrieverV2: 2-layer RAG retriever with RRF fusion

Combines BM25 and Vector search using Reciprocal Rank Fusion (RRF).
Returns results in standardized format with 'fused_results' key.

Architecture:
    BM25 (keyword) ──┐
                     ├─→ RRF Fusion ─→ fused_results
    Vector (semantic)─┘

Example:
    >>> retriever = HybridRetrieverV2()
    >>> result = retriever.search("DVR 최근 구매", top_k=5)
    >>> for doc in result["fused_results"]:
    ...     print(doc["id"], doc["score"])
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict

from app.core.logging import get_logger
from app.rag.db import MetadataDB
from app.rag.index_bm25 import BM25Index
from app.rag.index_vec import VectorIndex

logger = get_logger(__name__)

# 진단 모드 설정
DIAG_RAG = os.getenv('DIAG_RAG', 'false').lower() == 'true'
DIAG_LOG_LEVEL = os.getenv('DIAG_LOG_LEVEL', 'INFO').upper()


class HybridRetrieverV2:
    """Hybrid retriever with BM25 + Vector + RRF

    Two-layer RAG architecture:
    1. Retrieval: BM25 + Vector → RRF fusion
    2. Generation: LLM with retrieved context (handled separately)

    Returns standardized 'fused_results' format for consistency.
    """

    def __init__(
        self,
        db_path: str = None,
        bm25_index_dir: str = None,
        vec_index_dir: str = None,
        k_bm25: int = None,
        k_vec: int = None,
        rrf_k: int = None,
    ):
        """Initialize hybrid retriever

        Args:
            db_path: Path to metadata.db (default from METADATA_DB_PATH env)
            bm25_index_dir: BM25 index directory (default from .env)
            vec_index_dir: Vector index directory (default from .env)
            k_bm25: Top-K for BM25 search (default from env or 20)
            k_vec: Top-K for vector search (default from env or 20)
            rrf_k: RRF constant (default 60)
        """
        # CRITICAL: Load paths from .env ONLY (no hardcoded fallback)
        db_path = db_path or os.getenv('METADATA_DB_PATH')
        if not db_path:
            raise ValueError("METADATA_DB_PATH not set in .env")

        # Extract directory from BM25_INDEX_PATH if full path provided
        bm25_path = bm25_index_dir or os.getenv('BM25_INDEX_PATH')
        if not bm25_path:
            raise ValueError("BM25_INDEX_PATH not set in .env")
        bm25_index_dir = os.path.dirname(bm25_path) if bm25_path.endswith('.pkl') else bm25_path

        # Extract directory from VECTOR_INDEX_PATH if full path provided
        vec_path = vec_index_dir or os.getenv('VECTOR_INDEX_PATH')
        if not vec_path:
            raise ValueError("VECTOR_INDEX_PATH not set in .env")
        vec_index_dir = os.path.dirname(vec_path) if vec_path.endswith('.index') else vec_path

        # Load search parameters from environment
        self.k_bm25 = k_bm25 or int(os.getenv('SEARCH_BM25_TOP_K', '20'))
        self.k_vec = k_vec or int(os.getenv('SEARCH_VEC_TOP_K', '20'))
        self.rrf_k = rrf_k or int(os.getenv('SEARCH_RRF_K', '60'))

        # Initialize components
        self.db = MetadataDB(db_path)
        self.bm25 = BM25Index(bm25_index_dir)
        self.vec = VectorIndex(vec_index_dir)

        # CRITICAL: 인덱스 검증 (부팅 시 필수)
        bm25_count = len(self.bm25.doc_ids)
        vec_count = len(self.vec.doc_ids)

        logger.info(f"✅ BM25 인덱스 로드 완료: {bm25_count}개 문서")
        logger.info(f"✅ FAISS 인덱스 로드 완료: {vec_count}개 문서 (dim={self.vec.embedding_dim})")

        # 인덱스 개수 검증
        if bm25_count == 0:
            error_msg = f"❌ BM25 인덱스가 비어있습니다 (0개 문서). 인덱스 재구축 필요: python3 scripts/rebuild_indexes_v2.py"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if vec_count == 0:
            error_msg = f"❌ FAISS 인덱스가 비어있습니다 (0개 문서). 인덱스 재구축 필요: python3 scripts/rebuild_indexes_v2.py"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if bm25_count != vec_count:
            error_msg = f"⚠️  인덱스 불일치: BM25={bm25_count}, FAISS={vec_count}. 인덱스 재구축 권장"
            logger.warning(error_msg)

        logger.info(
            f"HybridRetrieverV2 initialized: "
            f"BM25={bm25_count} docs, Vec={vec_count} docs, "
            f"k_bm25={self.k_bm25}, k_vec={self.k_vec}, rrf_k={self.rrf_k}"
        )

    def _rrf_fusion(
        self,
        bm25_results: List[Dict[str, Any]],
        vec_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion (RRF)

        RRF score = sum(1 / (k + rank)) for each result list

        Args:
            bm25_results: BM25 search results
            vec_results: Vector search results

        Returns:
            Fused results sorted by RRF score
        """
        rrf_scores = defaultdict(float)

        # Add BM25 scores
        for result in bm25_results:
            doc_id = result['id']
            rank = result['rank']
            rrf_scores[doc_id] += 1.0 / (self.rrf_k + rank)

        # Add vector scores
        for result in vec_results:
            doc_id = result['id']
            rank = result['rank']
            rrf_scores[doc_id] += 1.0 / (self.rrf_k + rank)

        # Sort by RRF score
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Build result list
        fused = []
        for rank, (doc_id, score) in enumerate(sorted_docs, 1):
            fused.append({
                'id': doc_id,
                'score': float(score),
                'rank': rank,
            })

        return fused

    def _extract_author_query(self, query: str) -> Tuple[Optional[str], List[str]]:
        """저자 질의 의도 추출 및 쿼리 확장

        Args:
            query: 원본 검색 쿼리

        Returns:
            (author_name, expanded_queries) tuple
            - author_name: 추출된 저자 이름 (없으면 None)
            - expanded_queries: 확장된 쿼리 리스트 (저자 의도가 없으면 [query])
        """
        # 저자 의도 패턴: "이름이/가 작성/기안/제안한 문서"
        patterns = [
            r"([가-힣\s]+)\s*(?:이|가)?\s*(?:작성|기안|제안)\s*(?:한|하신)?\s*(?:문서|자료|기안서)?",
            r"(?:작성자|기안자|제안자)[\s:]*([가-힣\s]+)",
            r"([가-힣\s]+)\s+(?:기안서|작성문서)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                author_name = match.group(1).strip()
                logger.info(f"저자 의도 감지: '{author_name}' (원본 쿼리: '{query}')")

                # 쿼리 확장: 메타 필드 + OCR 텍스트 양쪽 매칭
                expanded_queries = [
                    f"{author_name}",           # 기본 이름 검색
                    f"기안자 {author_name}",     # OCR 텍스트 내 표현
                    f"작성자 {author_name}",
                    f"{author_name} 기안서",
                    f"{author_name} 문서",
                ]

                logger.info(f"쿼리 확장: {len(expanded_queries)}개 변형 생성")
                return (author_name, expanded_queries)

        # 저자 의도가 없는 일반 쿼리
        return (None, [query])

    def search(
        self,
        query: str,
        top_k: int = 5,
        k_bm25: int = None,
        k_vec: int = None,
    ) -> Dict[str, Any]:
        """Search documents using hybrid retrieval

        Args:
            query: Search query
            top_k: Number of final results to return
            k_bm25: Top-K for BM25 (override default)
            k_vec: Top-K for vector (override default)

        Returns:
            Dictionary with key 'fused_results':
            {
                "fused_results": [
                    {
                        "id": "doc_4094",
                        "score": 0.123,
                        "rank": 1,
                        "title": "...",
                        "filename": "...",
                        "date": "...",
                        ...
                    },
                    ...
                ]
            }
        """
        if not query or not query.strip():
            logger.warning("Empty query")
            return {"fused_results": []}

        k_bm25 = k_bm25 or self.k_bm25
        k_vec = k_vec or self.k_vec

        # 저자 질의 확장 (리콜 향상)
        author_name, expanded_queries = self._extract_author_query(query)

        try:
            # 확장 쿼리로 여러 검색 수행 후 융합 (저자 질의인 경우)
            if author_name and len(expanded_queries) > 1:
                logger.info(f"저자 질의 모드: {len(expanded_queries)}개 확장 쿼리로 검색")
                all_bm25_results = []
                all_vec_results = []

                # 각 확장 쿼리로 검색
                for i, exp_query in enumerate(expanded_queries, 1):
                    # BM25 검색 (낮은 top_k 사용)
                    bm25_part = self.bm25.search(exp_query, top_k=max(5, k_bm25 // len(expanded_queries)))
                    all_bm25_results.extend(bm25_part)

                    # Vector 검색 (낮은 top_k 사용)
                    vec_part = self.vec.search(exp_query, top_k=max(5, k_vec // len(expanded_queries)))
                    all_vec_results.extend(vec_part)

                # 중복 제거 (doc_id 기준 최고 rank 유지)
                bm25_dedup = {}
                for r in all_bm25_results:
                    doc_id = r['id']
                    if doc_id not in bm25_dedup or r['rank'] < bm25_dedup[doc_id]['rank']:
                        bm25_dedup[doc_id] = r

                vec_dedup = {}
                for r in all_vec_results:
                    doc_id = r['id']
                    if doc_id not in vec_dedup or r['rank'] < vec_dedup[doc_id]['rank']:
                        vec_dedup[doc_id] = r

                bm25_results = list(bm25_dedup.values())
                vec_results = list(vec_dedup.values())

                logger.info(
                    f"확장 쿼리 검색 완료: BM25={len(bm25_results)} (중복제거 후), "
                    f"Vec={len(vec_results)} (중복제거 후)"
                )
            else:
                # 일반 검색 (저자 의도가 없는 경우)
                # 1. BM25 search
                logger.info(f"BM25 search: '{query}' (top_k={k_bm25})")
                bm25_results = self.bm25.search(query, top_k=k_bm25)

            # [DIAG] BM25 검색 결과
            if DIAG_RAG and DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                logger.info(f"[DIAG] BM25 검색 완료: {len(bm25_results)}개 문서")
                if DIAG_LOG_LEVEL == 'DEBUG' and bm25_results:
                    top3_bm25 = bm25_results[:3]
                    logger.debug(f"[DIAG] BM25 상위 3개: {[r['id'] for r in top3_bm25]}")

            # 2. Vector search
            logger.info(f"Vector search: '{query}' (top_k={k_vec})")
            vec_results = self.vec.search(query, top_k=k_vec)

            # [DIAG] Vector 검색 결과
            if DIAG_RAG and DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                logger.info(f"[DIAG] Vector 검색 완료: {len(vec_results)}개 문서")
                if DIAG_LOG_LEVEL == 'DEBUG' and vec_results:
                    top3_vec = vec_results[:3]
                    logger.debug(f"[DIAG] Vector 상위 3개: {[r['id'] for r in top3_vec]}")

            # 3. RRF fusion
            fused_results = self._rrf_fusion(bm25_results, vec_results)

            # [DIAG] RRF 융합 결과
            if DIAG_RAG and DIAG_LOG_LEVEL in ['DEBUG', 'INFO']:
                logger.info(
                    f"[DIAG] RRF 융합 완료: BM25({len(bm25_results)}) + Vec({len(vec_results)}) "
                    f"→ {len(fused_results)}개 (k={self.rrf_k})"
                )

            # 4. Enrich with metadata from database
            enriched_results = []
            for result in fused_results[:top_k]:
                doc_id = result['id']
                meta = self.db.get_meta(doc_id)

                enriched_results.append({
                    'id': doc_id,
                    'score': result['score'],
                    'rank': result['rank'],
                    'title': meta.get('title', ''),
                    'filename': meta.get('filename', ''),
                    'date': meta.get('date', ''),
                    'year': meta.get('year', ''),
                    'month': meta.get('month', ''),
                    'category': meta.get('category', ''),
                    'drafter': meta.get('drafter', ''),
                    'page_count': meta.get('page_count', 0),
                    'path': meta.get('path', ''),
                })

            # 저자 매칭 부스팅 (soft filter: 완전 제거하지 않고 우선순위 상승)
            if author_name:
                author_match_count = 0
                for doc in enriched_results:
                    drafter = doc.get('drafter', '')
                    if author_name in drafter or drafter in author_name:
                        # 저자 매칭: 점수 2배 부스팅
                        doc['score'] *= 2.0
                        doc['author_match'] = True
                        author_match_count += 1
                        logger.debug(
                            f"저자 매칭: {doc['id']} (drafter='{drafter}', "
                            f"score boosted to {doc['score']:.4f})"
                        )
                    else:
                        doc['author_match'] = False

                # 부스팅 후 재정렬
                enriched_results.sort(key=lambda x: x['score'], reverse=True)

                logger.info(
                    f"저자 부스팅 완료: {author_match_count}/{len(enriched_results)}개 "
                    f"문서가 저자 '{author_name}'와 매칭됨"
                )

            # [DIAG] 최종 결과 스냅샷
            if DIAG_RAG and DIAG_LOG_LEVEL == 'DEBUG' and enriched_results:
                for i, r in enumerate(enriched_results[:3], 1):
                    logger.debug(
                        f"[DIAG] Final[{i}]: {r['id']} (score={r['score']:.4f}), "
                        f"filename={r.get('filename', 'N/A')}, drafter={r.get('drafter', 'N/A')}"
                    )

            logger.info(
                f"Hybrid search complete: '{query}' → "
                f"{len(bm25_results)} BM25 + {len(vec_results)} Vec → "
                f"{len(enriched_results)} fused"
            )

            return {"fused_results": enriched_results}

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return {"fused_results": []}

    def get_content(self, doc_id: str) -> str:
        """Get document content from database

        Args:
            doc_id: Document ID (e.g., "doc_4094")

        Returns:
            Document text content
        """
        return self.db.get_content(doc_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get retriever statistics

        Returns:
            Dictionary with statistics from all components
        """
        return {
            'bm25': self.bm25.get_stats(),
            'vector': self.vec.get_stats(),
            'database': {
                'total_documents': self.db.count_documents(),
                'db_path': str(self.db.db_path),
            },
            'parameters': {
                'k_bm25': self.k_bm25,
                'k_vec': self.k_vec,
                'rrf_k': self.rrf_k,
            },
        }
