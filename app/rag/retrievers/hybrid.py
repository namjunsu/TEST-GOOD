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
                    # 🔥 HOTFIX: snippet 폴백 체인 (text → content → preview → text_preview)
                    snippet = (
                        (r.get("text") or "").strip()
                        or (r.get("content") or "").strip()
                        or (r.get("preview") or "").strip()
                        or (r.get("text_preview") or "").strip()
                        or (r.get("snippet") or "").strip()
                    )

                    # snippet이 여전히 비어있으면 DB에서 페이지 텍스트 로드 시도
                    if not snippet:
                        filename = r.get("filename")
                        if filename and hasattr(self.rag, "metadata_db"):
                            try:
                                # DB에서 text_preview 조회
                                from modules.metadata_db import MetadataDB
                                db_text = self.rag.metadata_db.get_text_preview(filename)
                                if db_text:
                                    snippet = db_text.strip()
                                    logger.debug(f"snippet_filled from=db_preview filename={filename}")
                            except Exception as e:
                                logger.debug(f"DB 조회 실패: {e}")

                    # 최종 안전장치: 여전히 비어있으면 파일명이라도 표시
                    if not snippet:
                        snippet = f"[{r.get('filename', 'unknown')}]"
                        logger.warning(f"⚠️ snippet 비어있음, fallback to filename: {r.get('filename')}")

                    normalized.append({
                        "doc_id": r.get("filename", "unknown"),
                        "page": 1,  # 페이지 정보 없음
                        "score": r.get("score", 0.0),
                        "snippet": snippet[:800],  # 스니펫 800자 상한
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
