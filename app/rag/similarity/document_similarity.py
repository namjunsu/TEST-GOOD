"""문서 유사도 계산 모듈

BM25 기반 문서 간 유사도를 계산하고 유사 문서를 추천합니다.
sentence-transformers 없이 기존 BM25 인덱스를 활용합니다.

2025-12-08: 초기 구현
2025-12-26: 메타데이터 기반 필터링 강화 (카테고리, 작성자, 날짜 유사도)
"""

import os
from datetime import datetime
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
        top_k: Optional[int] = None,
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
                base_score = min(1.0, score / divisor) if score > 1 else score

                # 문서 메타데이터 가져오기
                similar_doc = self._db.get_by_filename(result_id)
                if not similar_doc:
                    continue

                # 메타데이터 기반 유사도 보정 (2025-12-26)
                boosted_score = self._boost_similarity_with_metadata(
                    base_score, doc, similar_doc
                )

                if boosted_score >= self.min_similarity:
                    similar_docs.append({
                        "filename": result_id,
                        "title": similar_doc.get("title", result_id),
                        "similarity": round(boosted_score, 3),
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

        except (AttributeError, KeyError) as e:
            logger.warning(f"⚠️ 유사 문서 검색 - 데이터 접근 오류: {e}")
            return []
        except Exception as e:
            logger.exception(f"❌ 유사 문서 검색 예상치 못한 오류: {type(e).__name__}")
            return []

    def find_similar_by_query(
        self,
        query: str,
        reference_docs: list[str],
        top_k: Optional[int] = None,
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
            # 기준 문서들의 메타데이터 수집 (카테고리 필터링용)
            reference_metadata = []
            for ref_id in reference_docs[:3]:  # 최대 3개만 참조
                ref_meta = self._db.get_by_filename(ref_id)
                if ref_meta:
                    reference_metadata.append(ref_meta)

            search_buffer = DocumentSimilarityConfig.SEARCH_BUFFER
            search_results = self._retriever.search(
                query, top_k=top_k + len(reference_docs) + search_buffer,
            )

            similar_docs = []
            reference_set = set(reference_docs)

            # 원본 쿼리에서 핵심 키워드 추출 (불용어 제거)
            query_keywords = self._extract_query_keywords(query)

            for result in search_results:
                result_id = result.get("filename") or result.get("doc_id")

                # 이미 반환된 문서 제외
                if result_id in reference_set:
                    continue

                # BM25 점수 임계값 필터링 (2026-01-05)
                # 너무 낮은 점수는 관련성이 떨어지므로 제외
                raw_score = result.get("score", 0)
                if raw_score < DocumentSimilarityConfig.MIN_BM25_SCORE:
                    logger.debug(
                        f"⏭️ BM25 점수 미달로 제외: {result_id[:40]} "
                        f"(score={raw_score:.2f} < {DocumentSimilarityConfig.MIN_BM25_SCORE})"
                    )
                    continue

                # 점수 정규화 (0-1)
                divisor = DocumentSimilarityConfig.SCORE_NORMALIZE_DIVISOR
                base_score = min(1.0, raw_score / divisor) if raw_score > 1 else raw_score

                # 문서 메타데이터 가져오기
                similar_doc = self._db.get_by_filename(result_id)
                if not similar_doc:
                    continue

                # 🔍 원본 쿼리 키워드 검증 (2026-01-05)
                # 유사 문서라도 원본 쿼리와 관련 없으면 제외
                if not self._matches_query_keywords(similar_doc, query_keywords):
                    logger.debug(
                        f"⏭️ 쿼리 키워드 미포함으로 제외: {result_id} "
                        f"(keywords={query_keywords})"
                    )
                    continue

                # 메타데이터 기반 유사도 보정 (2025-12-26)
                # 기준: 첫 번째 reference 문서와 비교
                if reference_metadata:
                    boosted_score = self._boost_similarity_with_metadata(
                        base_score, reference_metadata[0], similar_doc
                    )
                else:
                    boosted_score = base_score

                if boosted_score >= self.min_similarity:
                    similar_docs.append({
                        "filename": result_id,
                        "title": similar_doc.get("title", result_id),
                        "similarity": round(boosted_score, 3),
                        "date": similar_doc.get("display_date") or similar_doc.get("date", ""),
                        "drafter": similar_doc.get("drafter", ""),
                        "category": similar_doc.get("category", ""),
                    })

                if len(similar_docs) >= top_k:
                    break

            logger.info(f"📊 쿼리 기반 유사 문서 {len(similar_docs)}건 발견: '{query[:30]}...'")
            return similar_docs

        except (AttributeError, KeyError) as e:
            logger.warning(f"⚠️ 쿼리 기반 유사 문서 검색 - 데이터 접근 오류: {e}")
            return []
        except Exception as e:
            logger.exception(f"❌ 쿼리 기반 유사 문서 검색 예상치 못한 오류: {type(e).__name__}")
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

    def _boost_similarity_with_metadata(
        self,
        base_score: float,
        ref_doc: dict,
        candidate_doc: dict,
    ) -> float:
        """메타데이터 기반 유사도 보정

        Args:
            base_score: BM25 기반 기본 점수 (0-1)
            ref_doc: 기준 문서 메타데이터
            candidate_doc: 후보 문서 메타데이터

        Returns:
            보정된 유사도 점수 (0-1, 최대 1.0)
        """
        boosted_score = base_score
        bonuses_applied = []

        # 1. 카테고리 일치 보너스
        ref_category = ref_doc.get("category", "")
        cand_category = candidate_doc.get("category", "")
        if ref_category and cand_category and ref_category == cand_category:
            boosted_score += DocumentSimilarityConfig.CATEGORY_MATCH_BONUS
            bonuses_applied.append(f"category({ref_category})")

        # 2. 작성자 일치 보너스
        ref_drafter = ref_doc.get("drafter", "")
        cand_drafter = candidate_doc.get("drafter", "")
        if ref_drafter and cand_drafter and ref_drafter == cand_drafter:
            boosted_score += DocumentSimilarityConfig.DRAFTER_MATCH_BONUS
            bonuses_applied.append(f"drafter({ref_drafter})")

        # 3. 날짜 근접성 보너스 (1년 이내)
        ref_date = self._parse_date(ref_doc.get("date", ""))
        cand_date = self._parse_date(candidate_doc.get("date", ""))
        if ref_date and cand_date:
            days_diff = abs((ref_date - cand_date).days)
            if days_diff <= 365:  # 1년 이내
                boosted_score += DocumentSimilarityConfig.DATE_PROXIMITY_BONUS
                bonuses_applied.append(f"date({days_diff}d)")

        # 로깅 (보너스가 적용된 경우만)
        if bonuses_applied and boosted_score > base_score:
            cand_filename = candidate_doc.get("filename", "")[:40]
            logger.debug(
                f"📊 유사도 보정: {cand_filename}... "
                f"{base_score:.2f} → {min(1.0, boosted_score):.2f} "
                f"[{', '.join(bonuses_applied)}]"
            )

        # 최대 1.0으로 제한
        return min(1.0, boosted_score)

    def _extract_query_keywords(self, query: str) -> set[str]:
        """쿼리에서 핵심 키워드 추출 (불용어 제거)

        Args:
            query: 원본 쿼리 (예: "유튜브 관련 문서 찾아줘")

        Returns:
            핵심 키워드 집합 (예: {"유튜브"})
        """
        # 기본 불용어 (조사, 어미 등)
        stopwords = {
            "관련", "문서", "찾아", "찾아줘", "보여줘", "알려줘", "검색",
            "있는", "없는", "있어", "없어", "해줘", "주세요",
            "은", "는", "이", "가", "을", "를", "에", "에서", "의",
            "과", "와", "도", "만", "부터", "까지", "로", "으로",
        }

        # 공백으로 분리하고 불용어 제거
        keywords = set()
        for word in query.split():
            word_clean = word.strip().lower()
            if word_clean and word_clean not in stopwords and len(word_clean) > 1:
                keywords.add(word_clean)

        return keywords

    def _matches_query_keywords(self, doc: dict, query_keywords: set[str]) -> bool:
        """문서가 쿼리 키워드를 포함하는지 검증

        Args:
            doc: 문서 메타데이터
            query_keywords: 검증할 키워드 집합

        Returns:
            하나 이상의 키워드를 포함하면 True
        """
        if not query_keywords:
            return True  # 키워드가 없으면 통과

        # 검색 대상: 제목 + 텍스트 미리보기 + 파일명
        search_text = " ".join([
            doc.get("title", ""),
            doc.get("text_preview", "")[:500],  # 미리보기 일부만
            doc.get("filename", ""),
        ]).lower()

        # 키워드 중 하나라도 포함되면 True
        for keyword in query_keywords:
            if keyword in search_text:
                return True

        return False

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """날짜 문자열을 datetime으로 변환

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD 형식)

        Returns:
            datetime 객체 또는 None
        """
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

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
