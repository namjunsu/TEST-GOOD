"""문서 유사도 계산 모듈

BM25 기반 문서 간 유사도를 계산하고 유사 문서를 추천합니다.
sentence-transformers 없이 기존 BM25 인덱스를 활용합니다.

2025-12-08: 초기 구현
"""

import os
from typing import Any, Optional

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from config.constants import DocumentSimilarityConfig

logger = get_logger(__name__)


class DocumentSimilarity:
    """문서 유사도 계산기 (BM25 기반)

    기존 BM25 인덱스와 메타데이터를 활용하여 유사 문서를 추천합니다.
    """

    def __init__(self, retriever=None):
        """초기화

        Args:
            retriever: HybridRetriever 인스턴스 (BM25 검색용)
        """
        self._db = MetadataDB()
        self._retriever = retriever
        self._cache: dict[str, list[dict]] = {}

        # 설정
        default_min = str(DocumentSimilarityConfig.DEFAULT_MIN_SIMILARITY)
        default_max = str(DocumentSimilarityConfig.DEFAULT_MAX_RESULTS)
        self.min_similarity = float(os.getenv("SIMILARITY_MIN_SCORE", default_min))
        self.max_results = int(os.getenv("SIMILARITY_MAX_RESULTS", default_max))

        logger.info(f"📊 DocumentSimilarity 초기화: min_score={self.min_similarity}, max_results={self.max_results}")

    def find_similar_documents(
        self,
        doc_id: str,
        top_k: int = None,
        exclude_self: bool = True,
    ) -> list[dict[str, Any]]:
        """특정 문서와 유사한 문서 찾기

        Args:
            doc_id: 기준 문서 ID (파일명)
            top_k: 반환할 최대 문서 수 (기본: self.max_results)
            exclude_self: 자기 자신 제외 여부

        Returns:
            유사 문서 목록 [{filename, title, similarity, ...}, ...]
        """
        top_k = top_k or self.max_results

        # 캐시 확인
        cache_key = f"{doc_id}:{top_k}"
        if cache_key in self._cache:
            logger.debug(f"📦 캐시 히트: {doc_id}")
            return self._cache[cache_key]

        try:
            # 1. 기준 문서 정보 가져오기
            doc = self._db.get_by_filename(doc_id)
            if not doc:
                logger.warning(f"⚠️ 문서를 찾을 수 없음: {doc_id}")
                return []

            # 2. 문서의 핵심 키워드 추출 (제목 + 텍스트 미리보기)
            keywords = self._extract_keywords(doc)
            if not keywords:
                logger.warning(f"⚠️ 키워드 추출 실패: {doc_id}")
                return []

            # 3. 키워드로 검색
            if not self._retriever:
                logger.warning("⚠️ Retriever가 없어 유사 문서 검색 불가")
                return []

            search_buffer = DocumentSimilarityConfig.SEARCH_BUFFER
            search_results = self._retriever.search(keywords, top_k=top_k + search_buffer)

            # 4. 결과 필터링 및 정리
            similar_docs = []
            for result in search_results:
                result_id = result.get("filename") or result.get("doc_id")

                # 자기 자신 제외
                if exclude_self and result_id == doc_id:
                    continue

                # 점수 정규화 (0-1)
                score = result.get("score", 0)
                divisor = DocumentSimilarityConfig.SCORE_NORMALIZE_DIVISOR
                normalized_score = min(1.0, score / divisor) if score > 1 else score

                if normalized_score >= self.min_similarity:
                    # 문서 메타데이터 가져오기
                    similar_doc = self._db.get_by_filename(result_id)
                    if similar_doc:
                        similar_docs.append({
                            "filename": result_id,
                            "title": similar_doc.get("title", result_id),
                            "similarity": round(normalized_score, 3),
                            "date": similar_doc.get("display_date") or similar_doc.get("date", ""),
                            "drafter": similar_doc.get("drafter", ""),
                            "category": similar_doc.get("category", ""),
                        })

                if len(similar_docs) >= top_k:
                    break

            # 캐시 저장
            self._cache[cache_key] = similar_docs

            logger.info(f"📊 유사 문서 {len(similar_docs)}건 발견: {doc_id}")
            return similar_docs

        except Exception as e:
            logger.error(f"❌ 유사 문서 검색 실패: {e}", exc_info=True)
            return []

    def find_similar_by_query(
        self,
        query: str,
        reference_docs: list[str],
        top_k: int = None,
    ) -> list[dict[str, Any]]:
        """쿼리 결과 문서들과 유사한 추가 문서 찾기

        Args:
            query: 원본 쿼리
            reference_docs: 이미 찾은 문서 ID 목록
            top_k: 반환할 최대 문서 수

        Returns:
            추가 유사 문서 목록
        """
        top_k = top_k or self.max_results

        if not reference_docs:
            return []

        # 2025-12-09: 원래 쿼리로 직접 검색 (첫 번째 문서 키워드 대신)
        # 이유: 문서 제목에서 키워드 추출 시 핵심 키워드가 누락될 수 있음
        if not self._retriever:
            logger.warning("⚠️ Retriever가 없어 유사 문서 검색 불가")
            return []

        try:
            search_buffer = DocumentSimilarityConfig.SEARCH_BUFFER
            search_results = self._retriever.search(
                query, top_k=top_k + len(reference_docs) + search_buffer,
            )

            similar_docs = []
            reference_set = set(reference_docs)

            for result in search_results:
                result_id = result.get("filename") or result.get("doc_id")

                # 이미 반환된 문서 제외
                if result_id in reference_set:
                    continue

                # 점수 정규화 (0-1)
                score = result.get("score", 0)
                divisor = DocumentSimilarityConfig.SCORE_NORMALIZE_DIVISOR
                normalized_score = min(1.0, score / divisor) if score > 1 else score

                if normalized_score >= self.min_similarity:
                    # 문서 메타데이터 가져오기
                    similar_doc = self._db.get_by_filename(result_id)
                    if similar_doc:
                        similar_docs.append({
                            "filename": result_id,
                            "title": similar_doc.get("title", result_id),
                            "similarity": round(normalized_score, 3),
                            "date": similar_doc.get("display_date") or similar_doc.get("date", ""),
                            "drafter": similar_doc.get("drafter", ""),
                            "category": similar_doc.get("category", ""),
                        })

                if len(similar_docs) >= top_k:
                    break

            logger.info(f"📊 쿼리 기반 유사 문서 {len(similar_docs)}건 발견: '{query[:30]}...'")
            return similar_docs

        except Exception as e:
            logger.error(f"❌ 쿼리 기반 유사 문서 검색 실패: {e}", exc_info=True)
            return []

    def _extract_keywords(self, doc: dict) -> str:
        """문서에서 검색용 키워드 추출

        Args:
            doc: 문서 메타데이터

        Returns:
            키워드 문자열
        """
        parts = []

        # 제목에서 키워드 추출
        title = doc.get("title", "")
        if title:
            # 날짜 패턴 제거
            import re
            title_clean = re.sub(r"\d{4}[-_]\d{2}[-_]\d{2}[-_]?", "", title)
            title_clean = title_clean.replace("_", " ").strip()
            if title_clean:
                parts.append(title_clean)

        # 카테고리
        category = doc.get("category", "")
        if category and category not in ["기타", "일반"]:
            parts.append(category)

        # 텍스트 미리보기에서 핵심 단어 추출
        preview_len = DocumentSimilarityConfig.TEXT_PREVIEW_LENGTH
        preview = doc.get("text_preview", "")[:preview_len]
        if preview:
            # 의미 있는 단어만 추출 (2자 이상 한글)
            import re
            words = re.findall(r"[가-힣]{2,}", preview)
            # 불용어 제거
            stopwords = {"있음", "없음", "있는", "없는", "하는", "되는", "위한", "대한", "따른"}
            max_kw = DocumentSimilarityConfig.MAX_KEYWORD_COUNT
            words = [w for w in words if w not in stopwords][:max_kw]
            parts.extend(words)

        return " ".join(parts)

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        logger.info("📦 유사도 캐시 초기화됨")


# 싱글톤 인스턴스
_similarity_instance: Optional[DocumentSimilarity] = None


def get_similarity_service(retriever=None) -> DocumentSimilarity:
    """DocumentSimilarity 싱글톤 인스턴스 반환"""
    global _similarity_instance
    if _similarity_instance is None:
        _similarity_instance = DocumentSimilarity(retriever=retriever)
    elif retriever and _similarity_instance._retriever is None:
        _similarity_instance._retriever = retriever
    return _similarity_instance
