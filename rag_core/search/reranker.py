"""
한국어 재순위화 모듈
=====================

검색 결과를 재순위화하여 정확도를 향상시킵니다.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
from sentence_transformers import CrossEncoder
import re
from collections import Counter

from ..config import RAGConfig
from ..exceptions import handle_errors

logger = logging.getLogger(__name__)


class KoreanReranker:
    """한국어 재순위화 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.cross_encoder = None
        self.use_cross_encoder = False  # CrossEncoder 사용 여부

        # 재순위화 가중치
        self.semantic_weight = 0.6
        self.keyword_weight = 0.2
        self.metadata_weight = 0.2

        # CrossEncoder 초기화 (선택적)
        self._init_cross_encoder()

    def _init_cross_encoder(self) -> None:
        """CrossEncoder 모델 초기화"""
        try:
            # 한국어 CrossEncoder 모델이 있다면 사용
            # 현재는 다국어 모델 사용
            model_name = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
            self.cross_encoder = CrossEncoder(model_name)
            self.use_cross_encoder = True
            logger.info("CrossEncoder initialized for reranking")
        except Exception as e:
            logger.warning(f"CrossEncoder not available: {e}")
            self.use_cross_encoder = False

    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """
        텍스트에서 키워드 추출

        Args:
            text: 입력 텍스트
            top_n: 추출할 키워드 수

        Returns:
            키워드 리스트
        """
        # 한글, 영문, 숫자만 추출
        words = re.findall(r'[가-힣]+|[a-zA-Z]+|\d+', text.lower())

        # 2글자 이상만 필터링
        words = [w for w in words if len(w) >= 2]

        # 빈도수 계산
        word_counts = Counter(words)

        # 상위 키워드 반환
        return [word for word, _ in word_counts.most_common(top_n)]

    def _calculate_keyword_score(
        self,
        query: str,
        text: str
    ) -> float:
        """
        키워드 기반 점수 계산

        Args:
            query: 검색 쿼리
            text: 문서 텍스트

        Returns:
            키워드 매칭 점수 (0-1)
        """
        # 쿼리 키워드 추출
        query_keywords = set(self._extract_keywords(query))

        if not query_keywords:
            return 0.0

        # 텍스트 키워드 추출
        text_keywords = set(self._extract_keywords(text, top_n=50))

        # Jaccard 유사도
        intersection = query_keywords & text_keywords
        union = query_keywords | text_keywords

        if not union:
            return 0.0

        jaccard_score = len(intersection) / len(union)

        # TF 점수 (쿼리 키워드의 출현 빈도)
        text_lower = text.lower()
        tf_scores = []
        for keyword in query_keywords:
            count = text_lower.count(keyword)
            # 로그 스케일링
            tf_score = np.log1p(count) / np.log1p(len(text_lower.split()))
            tf_scores.append(tf_score)

        tf_score = np.mean(tf_scores) if tf_scores else 0.0

        # 최종 점수 (Jaccard 70%, TF 30%)
        final_score = jaccard_score * 0.7 + tf_score * 0.3

        return min(final_score, 1.0)

    def _calculate_metadata_score(
        self,
        query: str,
        metadata: Dict
    ) -> float:
        """
        메타데이터 기반 점수 계산

        Args:
            query: 검색 쿼리
            metadata: 문서 메타데이터

        Returns:
            메타데이터 매칭 점수 (0-1)
        """
        score = 0.0
        query_lower = query.lower()

        # 제목 매칭
        title = metadata.get('title', '').lower()
        if title and title in query_lower:
            score += 0.4
        elif title and query_lower in title:
            score += 0.3

        # 카테고리 매칭
        category = metadata.get('category', '').lower()
        if category:
            if '구매' in query_lower and category == 'purchase':
                score += 0.2
            elif '수리' in query_lower and category == 'repair':
                score += 0.2
            elif '폐기' in query_lower and category == 'disposal':
                score += 0.2

        # 연도 매칭
        year = metadata.get('year', '')
        if year and str(year) in query:
            score += 0.2

        # 날짜 매칭
        date = metadata.get('date', '')
        if date and date in query:
            score += 0.2

        return min(score, 1.0)

    @handle_errors(default_return=[])
    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_k: int = 5
    ) -> List[Dict]:
        """
        검색 결과 재순위화

        Args:
            query: 검색 쿼리
            results: 검색 결과 리스트
            top_k: 반환할 결과 수

        Returns:
            재순위화된 결과 리스트
        """
        if not results:
            return []

        logger.info(f"Reranking {len(results)} results")

        # CrossEncoder 사용 가능한 경우
        if self.use_cross_encoder and self.cross_encoder:
            pairs = [[query, r['text'][:512]] for r in results]  # 텍스트 길이 제한
            ce_scores = self.cross_encoder.predict(pairs)

            # 정규화
            if len(ce_scores) > 0:
                min_score = ce_scores.min()
                max_score = ce_scores.max()
                if max_score > min_score:
                    ce_scores = (ce_scores - min_score) / (max_score - min_score)
                else:
                    ce_scores = np.ones_like(ce_scores) * 0.5
        else:
            ce_scores = np.zeros(len(results))

        # 각 결과에 대한 종합 점수 계산
        for i, result in enumerate(results):
            # 시맨틱 점수 (CrossEncoder 또는 기존 점수 사용)
            if self.use_cross_encoder:
                semantic_score = float(ce_scores[i])
            else:
                # 기존 하이브리드 점수 사용
                semantic_score = result.get('score', 0.0)

            # 키워드 점수
            keyword_score = self._calculate_keyword_score(
                query,
                result.get('text', '')[:1000]  # 처음 1000자만 사용
            )

            # 메타데이터 점수
            metadata_score = self._calculate_metadata_score(
                query,
                result.get('metadata', {})
            )

            # 종합 점수 계산
            final_score = (
                semantic_score * self.semantic_weight +
                keyword_score * self.keyword_weight +
                metadata_score * self.metadata_weight
            )

            # 결과에 점수 추가
            result['rerank_score'] = final_score
            result['semantic_score'] = semantic_score
            result['keyword_score'] = keyword_score
            result['metadata_score'] = metadata_score

        # 재순위화 점수로 정렬
        results.sort(key=lambda x: x['rerank_score'], reverse=True)

        # top_k개만 반환
        reranked_results = results[:top_k]

        logger.info(f"Reranking completed, returning {len(reranked_results)} results")
        return reranked_results

    def batch_rerank(
        self,
        queries: List[str],
        results_list: List[List[Dict]],
        top_k: int = 5
    ) -> List[List[Dict]]:
        """
        배치 재순위화

        Args:
            queries: 쿼리 리스트
            results_list: 각 쿼리에 대한 결과 리스트
            top_k: 각 쿼리당 반환할 결과 수

        Returns:
            재순위화된 결과 리스트들
        """
        reranked_list = []

        for query, results in zip(queries, results_list):
            reranked = self.rerank(query, results, top_k)
            reranked_list.append(reranked)

        return reranked_list

    def update_weights(
        self,
        semantic_weight: float,
        keyword_weight: float,
        metadata_weight: float
    ) -> None:
        """
        재순위화 가중치 업데이트

        Args:
            semantic_weight: 시맨틱 가중치
            keyword_weight: 키워드 가중치
            metadata_weight: 메타데이터 가중치
        """
        # 정규화
        total = semantic_weight + keyword_weight + metadata_weight
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
        self.metadata_weight = metadata_weight / total

        logger.info(
            f"Updated reranker weights - "
            f"Semantic: {self.semantic_weight:.2f}, "
            f"Keyword: {self.keyword_weight:.2f}, "
            f"Metadata: {self.metadata_weight:.2f}"
        )