"""하이브리드 검색 엔진 (MetadataDB 기반 임시 구현)

QuickFixRAG가 제거되어 MetadataDB를 사용한 간단한 검색으로 대체
"""

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

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """검색 수행

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            정규화된 검색 결과 리스트:
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

            # MetadataDB에서 검색
            results = self.metadata_db.search_documents(
                year=year,
                drafter=drafter,
                limit=top_k
            )

            # 결과 정규화
            normalized = []
            for idx, doc in enumerate(results):
                snippet = (doc.get('text_preview') or doc.get('content') or "")[:800]
                if not snippet:
                    snippet = f"[{doc.get('filename', 'unknown')}]"

                normalized.append({
                    "doc_id": doc.get("filename", "unknown"),
                    "page": 1,
                    "score": 1.0 - (idx * 0.1),  # 간단한 스코어
                    "snippet": snippet,
                    "meta": {
                        "filename": doc.get("filename", ""),
                        "drafter": doc.get("drafter", ""),
                        "date": doc.get("date", ""),
                        "category": doc.get("category", "pdf"),
                        "doc_id": doc.get("filename", "unknown"),
                    }
                })

            logger.info(f"🔍 HybridRetriever: {len(normalized)}건 검색 완료")
            return normalized

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
