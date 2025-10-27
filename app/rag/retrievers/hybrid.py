"""하이브리드 검색 엔진 (QuickFixRAG 래퍼)

실제 검색은 QuickFixRAG의 SearchModuleHybrid를 사용합니다.
"""

from typing import List, Dict, Any
from app.core.logging import get_logger

logger = get_logger(__name__)


class HybridRetriever:
    """하이브리드 검색 엔진 (QuickFixRAG 래퍼)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 QuickFixRAG의 검색 모듈을 사용합니다.
    """

    def __init__(self):
        """초기화 - QuickFixRAG 검색 모듈 로드"""
        try:
            from quick_fix_rag import QuickFixRAG
            self.rag = QuickFixRAG(use_hybrid=True)
            logger.info("✅ HybridRetriever 초기화 완료 (QuickFixRAG 래퍼)")
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
            # QuickFixRAG의 검색 모듈 사용
            if hasattr(self.rag, 'search_module'):
                # 하이브리드 검색 실행 (search_by_content 메서드 사용)
                results = self.rag.search_module.search_by_content(
                    query=query,
                    top_k=top_k,
                    mode="auto"  # auto 모드: basic/hybrid 자동 선택
                )

                # 정규화된 형식으로 변환
                normalized = []
                for r in results[:top_k]:
                    normalized.append({
                        "doc_id": r.get("filename", "unknown"),
                        "page": 1,  # 페이지 정보 없음
                        "score": r.get("score", 0.0),
                        "snippet": r.get("preview", "")[:400],  # 스니펫 400자
                        "meta": {
                            "filename": r.get("filename", ""),
                            "drafter": r.get("drafter", ""),
                            "date": r.get("date", ""),
                            "category": r.get("category", ""),
                            "doc_id": r.get("filename", "unknown"),
                        }
                    })

                logger.info(f"🔍 HybridRetriever: {len(normalized)}건 검색 완료")
                return normalized
            else:
                logger.warning("search_module 없음, 빈 결과 반환")
                return []

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
