"""하이브리드 검색 엔진 (MetadataDB 기반 임시 구현)

QuickFixRAG가 제거되어 MetadataDB를 사용한 간단한 검색으로 대체
"""

import os
import re
from typing import List, Dict, Any
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB
from app.rag.query_parser import QueryParser

logger = get_logger(__name__)


class HybridRetriever:
    """하이브리드 검색 엔진 (MetadataDB 기반)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 MetadataDB를 사용해 검색합니다.
    """

    def __init__(self):
        """초기화 - MetadataDB 로드"""
        try:
            # MetadataDB 초기화
            self.metadata_db = MetadataDB()
            self.known_drafters = self.metadata_db.list_unique_drafters()
            self.parser = QueryParser(self.known_drafters)
            logger.info("✅ HybridRetriever 초기화 완료 (MetadataDB 기반)")
        except Exception as e:
            logger.error(f"❌ HybridRetriever 초기화 실패: {e}")
            raise

    def _calculate_relevance_score(self, query: str, doc: Dict[str, Any]) -> float:
        """쿼리와 문서 간 relevance 스코어 계산 (BM25 유사)

        Args:
            query: 검색 질의
            doc: 문서 딕셔너리 (filename, text_preview 포함)

        Returns:
            0.0~1.0 범위의 relevance 스코어
        """
        # 쿼리 토큰화 (공백 + 특수문자 제거)
        query_tokens = set(re.findall(r'\w+', query.lower()))
        if not query_tokens:
            return 0.5  # 토큰 없으면 중립 스코어

        # 문서 텍스트 준비 (filename + text_preview)
        doc_text = (
            (doc.get('filename') or '') + ' ' +
            (doc.get('text_preview') or '') + ' ' +
            (doc.get('drafter') or '')
        ).lower()

        # 매칭된 토큰 수 계산
        matched_tokens = sum(1 for token in query_tokens if token in doc_text)

        # 기본 스코어: 매칭률
        match_ratio = matched_tokens / len(query_tokens)

        # 보너스: 완전 일치하는 구문이 있으면 가산점
        if query.lower() in doc_text:
            match_ratio = min(1.0, match_ratio + 0.3)

        # 페널티: 문서가 너무 짧으면 감점 (신뢰도 저하)
        text_len = len(doc.get('text_preview') or '')
        if text_len < 100:
            match_ratio *= 0.7

        return max(0.0, min(1.0, match_ratio))

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """검색 수행

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            정규화된 검색 결과 리스트 (score_stats 속성 포함):
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
        try:
            # 쿼리 파싱
            filters = self.parser.parse_filters(query)
            year = filters.get('year')
            drafter = filters.get('drafter')

            # MetadataDB에서 검색 (top_k * 3배 가져와서 relevance 재정렬)
            results = self.metadata_db.search_documents(
                year=year,
                drafter=drafter,
                limit=top_k * 3  # 더 많이 가져와서 relevance로 재정렬
            )

            # 결과 정규화 + relevance 스코어 계산
            normalized = []
            for doc in results:
                snippet = (doc.get('text_preview') or doc.get('content') or "")[:800]
                if not snippet:
                    snippet = f"[{doc.get('filename', 'unknown')}]"

                # Relevance 스코어 계산 (패치 AC1-S1)
                relevance_score = self._calculate_relevance_score(query, doc)

                normalized.append({
                    "doc_id": doc.get("filename", "unknown"),
                    "page": 1,
                    "score": relevance_score,  # 실수 relevance 스코어
                    "snippet": snippet,
                    "meta": {
                        "filename": doc.get("filename", ""),
                        "drafter": doc.get("drafter", ""),
                        "date": doc.get("date", ""),
                        "category": doc.get("category", "pdf"),
                        "doc_id": doc.get("filename", "unknown"),
                    }
                })

            # Relevance 스코어 기준 정렬 후 top_k개만 선택
            normalized.sort(key=lambda x: x['score'], reverse=True)
            normalized = normalized[:top_k]

            # 스코어 분포 통계 계산 (low-confidence 가드레일용)
            scores = [r["score"] for r in normalized]
            top1 = scores[0] if len(scores) > 0 else 0.0
            top2 = scores[1] if len(scores) > 1 else 0.0
            top3 = scores[2] if len(scores) > 2 else 0.0

            score_stats = {
                "hits": len(normalized),
                "top1": top1,
                "top2": top2,
                "top3": top3,
                "delta12": max(0.0, top1 - top2),
                "delta13": max(0.0, top1 - top3)
            }

            # 결과 리스트에 score_stats 속성 추가 (duck typing)
            # QueryRouter가 getattr(results, "score_stats", {})로 접근 가능
            class ResultsWithStats(list):
                def __init__(self, items, stats):
                    super().__init__(items)
                    self.score_stats = stats

            results_with_stats = ResultsWithStats(normalized, score_stats)

            logger.info(
                f"🔍 HybridRetriever: {len(normalized)}건 검색 완료 "
                f"(top1={top1:.2f}, delta12={score_stats['delta12']:.2f})"
            )
            return results_with_stats

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
