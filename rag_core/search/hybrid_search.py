"""
하이브리드 검색 모듈
====================

BM25와 Vector 검색을 결합한 하이브리드 검색을 제공합니다.
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np

from .bm25_search import BM25Search
from .vector_search import VectorSearch
from .reranker import KoreanReranker
from ..config import RAGConfig
from ..exceptions import SearchException, handle_errors

logger = logging.getLogger(__name__)


class HybridSearch:
    """하이브리드 검색 엔진 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.bm25_search = BM25Search(config)
        self.vector_search = VectorSearch(config)
        self.reranker = KoreanReranker(config)

        # 가중치 설정
        self.bm25_weight = config.bm25_weight
        self.vector_weight = config.vector_weight

        # 정규화 방법
        self.normalization_method = 'min_max'  # 'min_max' or 'z_score'

    def build_index(self, documents: List[Dict]) -> None:
        """
        하이브리드 인덱스 구축

        Args:
            documents: 문서 딕셔너리 리스트
        """
        logger.info(f"Building hybrid index for {len(documents)} documents")

        # BM25 인덱스 구축
        self.bm25_search.build_index(documents)

        # Vector 인덱스 구축
        self.vector_search.build_index(documents)

        logger.info("Hybrid index built successfully")

    def load_index(self) -> bool:
        """저장된 인덱스 로드"""
        bm25_loaded = self.bm25_search.load_index()
        vector_loaded = self.vector_search.load_index()

        if bm25_loaded and vector_loaded:
            logger.info("Hybrid index loaded successfully")
            return True
        else:
            logger.warning("Failed to load hybrid index completely")
            return False

    def _normalize_scores(
        self,
        scores: List[float],
        method: str = 'min_max'
    ) -> List[float]:
        """
        점수 정규화

        Args:
            scores: 점수 리스트
            method: 정규화 방법 ('min_max' or 'z_score')

        Returns:
            정규화된 점수 리스트
        """
        if not scores:
            return []

        scores_array = np.array(scores)

        if method == 'min_max':
            min_score = scores_array.min()
            max_score = scores_array.max()

            if max_score == min_score:
                return [0.5] * len(scores)

            normalized = (scores_array - min_score) / (max_score - min_score)

        elif method == 'z_score':
            mean = scores_array.mean()
            std = scores_array.std()

            if std == 0:
                return [0.5] * len(scores)

            normalized = (scores_array - mean) / std
            # Sigmoid를 적용하여 0-1 범위로
            normalized = 1 / (1 + np.exp(-normalized))

        else:
            normalized = scores_array

        return normalized.tolist()

    def _combine_results(
        self,
        bm25_results: List[Dict],
        vector_results: List[Dict]
    ) -> List[Dict]:
        """
        BM25와 Vector 결과 결합

        Args:
            bm25_results: BM25 검색 결과
            vector_results: Vector 검색 결과

        Returns:
            결합된 검색 결과
        """
        # 결과를 문서 ID별로 그룹화
        combined = defaultdict(lambda: {
            'score': 0.0,
            'bm25_score': 0.0,
            'vector_score': 0.0,
            'text': '',
            'metadata': {},
            'sources': []
        })

        # BM25 결과 처리
        if bm25_results:
            bm25_scores = [r['score'] for r in bm25_results]
            normalized_bm25 = self._normalize_scores(bm25_scores, self.normalization_method)

            for result, norm_score in zip(bm25_results, normalized_bm25):
                doc_id = result['id']
                combined[doc_id]['bm25_score'] = norm_score
                combined[doc_id]['score'] += norm_score * self.bm25_weight
                combined[doc_id]['text'] = result['text']
                combined[doc_id]['metadata'] = result['metadata']
                combined[doc_id]['sources'].append('bm25')

        # Vector 결과 처리
        if vector_results:
            vector_scores = [r['score'] for r in vector_results]
            normalized_vector = self._normalize_scores(vector_scores, self.normalization_method)

            for result, norm_score in zip(vector_results, normalized_vector):
                doc_id = result['id']
                combined[doc_id]['vector_score'] = norm_score
                combined[doc_id]['score'] += norm_score * self.vector_weight
                if not combined[doc_id]['text']:
                    combined[doc_id]['text'] = result['text']
                    combined[doc_id]['metadata'] = result['metadata']
                combined[doc_id]['sources'].append('vector')

        # 딕셔너리를 리스트로 변환
        results = []
        for doc_id, data in combined.items():
            result = {
                'id': doc_id,
                'score': data['score'],
                'bm25_score': data['bm25_score'],
                'vector_score': data['vector_score'],
                'text': data['text'],
                'metadata': data['metadata'],
                'sources': data['sources'],
                'type': 'hybrid'
            }
            results.append(result)

        # 점수 기준으로 정렬
        results.sort(key=lambda x: x['score'], reverse=True)

        return results

    @handle_errors(default_return=[])
    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
        use_reranker: bool = True
    ) -> List[Dict]:
        """
        하이브리드 검색 수행

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            min_score: 최소 점수 임계값
            use_reranker: 재순위화 사용 여부

        Returns:
            검색 결과 리스트
        """
        logger.info(f"Hybrid search for query: {query[:50]}")

        # 각각 top_k * 2개씩 검색 (재순위화를 위한 여유분)
        search_k = top_k * 2 if use_reranker else top_k

        # BM25 검색
        bm25_results = self.bm25_search.search(query, search_k)

        # Vector 검색
        vector_results = self.vector_search.search(query, search_k)

        # 결과 결합
        combined_results = self._combine_results(bm25_results, vector_results)

        # 재순위화
        if use_reranker and combined_results:
            combined_results = self.reranker.rerank(query, combined_results, top_k)
        else:
            combined_results = combined_results[:top_k]

        # 최소 점수 필터링
        filtered_results = [
            r for r in combined_results
            if r['score'] >= min_score
        ]

        logger.info(f"Hybrid search returned {len(filtered_results)} results")
        return filtered_results

    def search_with_filters(
        self,
        query: str,
        filters: Dict,
        top_k: int = 10
    ) -> List[Dict]:
        """
        필터가 적용된 하이브리드 검색

        Args:
            query: 검색 쿼리
            filters: 필터 조건 (예: {'year': '2024', 'category': 'purchase'})
            top_k: 반환할 최대 결과 수

        Returns:
            필터링된 검색 결과
        """
        # 기본 검색 수행 (더 많은 결과 가져오기)
        results = self.search(query, top_k * 3, use_reranker=False)

        # 필터 적용
        filtered_results = []
        for result in results:
            metadata = result.get('metadata', {})

            # 모든 필터 조건 확인
            match = True
            for key, value in filters.items():
                if metadata.get(key) != value:
                    match = False
                    break

            if match:
                filtered_results.append(result)

            # top_k개 수집되면 중단
            if len(filtered_results) >= top_k:
                break

        # 재순위화
        if filtered_results:
            filtered_results = self.reranker.rerank(query, filtered_results, top_k)

        logger.info(f"Filtered search returned {len(filtered_results)} results")
        return filtered_results

    def update_weights(
        self,
        bm25_weight: float,
        vector_weight: float
    ) -> None:
        """
        검색 가중치 업데이트

        Args:
            bm25_weight: BM25 가중치
            vector_weight: Vector 가중치
        """
        # 정규화
        total = bm25_weight + vector_weight
        self.bm25_weight = bm25_weight / total
        self.vector_weight = vector_weight / total

        logger.info(f"Updated weights - BM25: {self.bm25_weight:.2f}, Vector: {self.vector_weight:.2f}")

    def get_stats(self) -> Dict:
        """
        인덱스 통계 반환

        Returns:
            통계 정보
        """
        bm25_stats = self.bm25_search.get_stats()
        vector_stats = self.vector_search.get_stats()

        return {
            'bm25': bm25_stats,
            'vector': vector_stats,
            'weights': {
                'bm25': self.bm25_weight,
                'vector': self.vector_weight
            },
            'normalization': self.normalization_method
        }