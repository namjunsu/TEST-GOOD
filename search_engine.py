"""
Search Engine Module
하이브리드 검색 엔진 (BM25 + Vector)
"""

import re
from typing import List, Dict, Any, Optional
from collections import defaultdict
import numpy as np
from rank_bm25 import BM25Okapi


class SearchEngine:
    """하이브리드 검색 엔진"""

    def __init__(self, config: Dict[str, Any], vector_store: 'VectorStore'):
        self.config = config
        self.vector_store = vector_store
        self.bm25_index = None
        self.chunk_ids = []

    def build_bm25_index(self, chunks: Dict[str, 'Chunk']) -> None:
        """BM25 인덱스 구축"""
        if not chunks:
            return

        # 청크 텍스트 수집
        texts = []
        self.chunk_ids = []

        for chunk_id, chunk in chunks.items():
            texts.append(chunk.content)
            self.chunk_ids.append(chunk_id)

        # 토큰화
        tokenized_texts = [self._tokenize_korean(text) for text in texts]

        # BM25 인덱스 생성
        self.bm25_index = BM25Okapi(tokenized_texts)

        print(f"✅ BM25 인덱스 구축 완료: {len(texts)}개 문서")

    def _tokenize_korean(self, text: str) -> List[str]:
        """한국어 토큰화 (간단 버전)"""
        # 특수문자 제거
        text = re.sub(r'[^\w\s]', ' ', text)

        # 공백으로 분리
        tokens = text.split()

        # 소문자 변환
        tokens = [t.lower() for t in tokens]

        return tokens

    def hybrid_search(
        self,
        query: str,
        documents: Dict[str, 'Document'],
        chunks: Dict[str, 'Chunk'],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """하이브리드 검색 (BM25 + Vector)"""

        results = []

        # 1. BM25 검색
        bm25_results = self._bm25_search(query, chunks, top_k * 2)

        # 2. 벡터 검색
        vector_results = self.vector_store.search(query, top_k * 2)

        # 3. 결과 병합 및 재순위
        merged_results = self._merge_results(bm25_results, vector_results)

        # 4. 최종 순위 결정
        final_results = self._rerank_results(merged_results, query, chunks)

        # 5. Top-K 선택
        for result in final_results[:top_k]:
            chunk_id = result['chunk_id']
            chunk = chunks.get(chunk_id)

            if chunk:
                doc = documents.get(chunk.doc_id)
                result['content'] = chunk.content
                result['metadata'] = chunk.metadata

                if doc:
                    result['document'] = {
                        'filename': doc.metadata.get('filename'),
                        'path': doc.metadata.get('path')
                    }

                results.append(result)

        return results

    def _bm25_search(
        self,
        query: str,
        chunks: Dict[str, 'Chunk'],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """BM25 검색"""
        if not self.bm25_index:
            self.build_bm25_index(chunks)

        # 쿼리 토큰화
        query_tokens = self._tokenize_korean(query)

        # BM25 점수 계산
        scores = self.bm25_index.get_scores(query_tokens)

        # Top-K 선택
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    'chunk_id': self.chunk_ids[idx],
                    'bm25_score': float(scores[idx]),
                    'type': 'bm25'
                })

        return results

    def _merge_results(
        self,
        bm25_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """검색 결과 병합"""
        merged = defaultdict(lambda: {
            'chunk_id': None,
            'bm25_score': 0.0,
            'vector_score': 0.0,
            'combined_score': 0.0
        })

        # BM25 결과 추가
        for result in bm25_results:
            chunk_id = result['chunk_id']
            merged[chunk_id]['chunk_id'] = chunk_id
            merged[chunk_id]['bm25_score'] = result['bm25_score']

        # 벡터 검색 결과 추가
        for result in vector_results:
            chunk_id = result['chunk_id']
            merged[chunk_id]['chunk_id'] = chunk_id
            merged[chunk_id]['vector_score'] = result['score']

        # 점수 정규화 및 결합
        results = []
        for chunk_id, scores in merged.items():
            # 정규화
            bm25_norm = self._normalize_score(scores['bm25_score'], 0, 10)
            vector_norm = scores['vector_score']  # 이미 정규화됨 (코사인 유사도)

            # 가중 평균 (BM25: 0.3, Vector: 0.7)
            combined = 0.3 * bm25_norm + 0.7 * vector_norm

            scores['combined_score'] = combined
            results.append(scores)

        # 점수 기준 정렬
        results.sort(key=lambda x: x['combined_score'], reverse=True)

        return results

    def _normalize_score(self, score: float, min_val: float, max_val: float) -> float:
        """점수 정규화 (0-1 범위)"""
        if max_val == min_val:
            return 0.5

        normalized = (score - min_val) / (max_val - min_val)
        return min(max(normalized, 0.0), 1.0)

    def _rerank_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        chunks: Dict[str, 'Chunk']
    ) -> List[Dict[str, Any]]:
        """결과 재순위 (추가 시그널 활용)"""

        query_lower = query.lower()
        query_tokens = set(self._tokenize_korean(query))

        for result in results:
            chunk_id = result['chunk_id']
            chunk = chunks.get(chunk_id)

            if chunk:
                content_lower = chunk.content.lower()

                # 추가 점수 계산
                boost = 0.0

                # 정확한 매칭 보너스
                if query_lower in content_lower:
                    boost += 0.2

                # 키워드 밀도
                token_matches = sum(1 for token in query_tokens if token in content_lower)
                boost += min(token_matches * 0.02, 0.1)

                # 메타데이터 매칭 (연도, 카테고리 등)
                metadata = chunk.metadata.get('doc_metadata', {})
                if any(str(v).lower() in query_lower for v in metadata.values()):
                    boost += 0.1

                # 최종 점수 업데이트
                result['final_score'] = result['combined_score'] + boost
            else:
                result['final_score'] = result['combined_score']

        # 최종 점수 기준 정렬
        results.sort(key=lambda x: x['final_score'], reverse=True)

        return results