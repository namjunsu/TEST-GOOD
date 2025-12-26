"""검색 결과 스코어링 모듈

문서 관련성 점수 계산 및 파일명 보너스 적용 로직을 제공합니다.
"""

import re
from typing import Any

from app.core.logging import get_logger
from config.constants import ScoringConfig

logger = get_logger(__name__)


class RelevanceScorer:
    """문서 관련성 점수 계산기

    쿼리와 문서 간의 관련성을 계산하고,
    파일명 매칭 보너스를 적용합니다.
    """

    def __init__(self, config: type = ScoringConfig):
        """초기화

        Args:
            config: 스코어링 설정 클래스
        """
        self.config = config

    def calculate_relevance_score(self, query: str, doc: dict[str, Any]) -> float:
        """쿼리와 문서 간 relevance 스코어 계산

        Args:
            query: 검색 질의
            doc: 문서 딕셔너리 (filename, snippet 포함)

        Returns:
            0.0~10.0 범위의 relevance 스코어
        """
        # 쿼리 토큰화
        query_tokens = set(re.findall(r"\w+", query.lower()))
        if not query_tokens:
            return 0.5  # 토큰 없으면 중립 스코어

        # 문서 텍스트 준비
        filename = (doc.get("filename") or "").lower()
        snippet = (doc.get("snippet") or "").lower()
        meta = doc.get("meta", {})
        drafter = (meta.get("drafter") or "").lower()
        doc_text = filename + " " + snippet + " " + drafter

        # 매칭된 토큰 수 계산
        matched_tokens = sum(1 for token in query_tokens if token in doc_text)

        # 기본 스코어: 매칭률
        match_ratio = matched_tokens / len(query_tokens) if query_tokens else 0.0

        # 보너스: 완전 일치하는 구문
        if query.lower() in doc_text:
            match_ratio = min(1.0, match_ratio + 0.3)

        # 페널티: 문서가 너무 짧으면 감점
        text_len = len(doc.get("snippet") or "")
        if text_len < 100:
            match_ratio *= 0.7

        # 안전장치: match_ratio가 0일 때 최소 epsilon 값
        if match_ratio == 0.0 and matched_tokens == 0:
            match_ratio = 1e-6

        # 파일명 매칭 보너스
        filename_bonus = self._calculate_filename_bonus(query, query_tokens, doc)

        # 날짜 가중치 (2025-12-26: Phase 2)
        date_bonus = self._calculate_date_bonus(doc, query)

        # 최종 스코어
        final_score = (match_ratio * self.config.MATCH_RATIO_SCALE) + filename_bonus + date_bonus

        if filename_bonus > 0 or date_bonus > 0:
            logger.debug(
                f"📊 Scoring '{filename[:50]}': match={match_ratio:.2f}, "
                f"filename_bonus={filename_bonus:.1f}, date_bonus={date_bonus:.1f}, "
                f"final={final_score:.1f}"
            )

        return max(0.0, min(self.config.MAX_FINAL_SCORE, final_score))

    def _calculate_filename_bonus(
        self, query: str, query_tokens: set[str], doc: dict[str, Any]
    ) -> float:
        """파일명 매칭 보너스 계산

        Args:
            query: 원본 쿼리
            query_tokens: 쿼리 토큰 집합
            doc: 문서 딕셔너리

        Returns:
            파일명 보너스 점수 (0.0~2.0)
        """
        filename = (doc.get("filename") or "").lower()
        filename_bonus = 0.0

        # 1. 토큰 매칭 보너스
        for token in query_tokens:
            if token in filename:
                filename_bonus += self.config.FILENAME_TOKEN_BONUS

        # 2. 전체 구문 매칭 보너스
        if len(query_tokens) >= 2 and query.lower() in filename:
            filename_bonus += self.config.FILENAME_PHRASE_BONUS

        # 3. n-gram 구문 매칭
        query_words = re.findall(r"\w+", query.lower())
        filename_clean = re.sub(r"[_\-\.]", " ", filename)

        ngram_bonus = 0.0
        for n in [3, 2]:  # 3-gram 우선
            if len(query_words) >= n:
                for i in range(len(query_words) - n + 1):
                    ngram = " ".join(query_words[i:i + n])
                    if ngram in filename_clean:
                        ngram_bonus += n * 0.2

        filename_bonus += min(1.0, ngram_bonus)

        # 4. 텍스트 길이 기반 페널티 (OCR 불량 문서 억제)
        text_len = len(doc.get("snippet") or "")
        if text_len < self.config.SHORT_TEXT_THRESHOLD:
            filename_bonus *= self.config.SHORT_TEXT_PENALTY
        elif text_len < self.config.VERY_SHORT_TEXT_THRESHOLD:
            filename_bonus *= self.config.VERY_SHORT_TEXT_PENALTY

        # 보너스 상한
        return min(self.config.FILENAME_BONUS_CAP, filename_bonus)

    def _calculate_date_bonus(self, doc: dict[str, Any], query: str) -> float:
        """시간 관련 쿼리 시 최신 문서에 보너스 부여

        Args:
            doc: 문서 딕셔너리 (meta.date 필드 필요)
            query: 검색 쿼리

        Returns:
            날짜 보너스 점수 (0.0~5.0)

        Examples:
            >>> # 시간 키워드 없음
            >>> scorer._calculate_date_bonus(doc, "무선 마이크 문서")
            0.0

            >>> # "현황" 키워드 + 1년 이내 문서
            >>> scorer._calculate_date_bonus(doc_2025, "광화문 티비로직 현황")
            5.0

            >>> # "현황" 키워드 + 2년 이내 문서
            >>> scorer._calculate_date_bonus(doc_2023, "광화문 티비로직 현황")
            0.0  # 2년 초과
        """
        # 시간 키워드 감지 (is_temporal_query와 동일)
        temporal_kw = ["현황", "현재", "최근", "최신", "지금", "상태"]
        if not any(kw in query for kw in temporal_kw):
            return 0.0

        # 날짜 파싱
        meta = doc.get("meta", {})
        date_str = meta.get("date", "")
        if not date_str:
            return 0.0

        # 연령 계산
        from datetime import datetime
        try:
            doc_date = datetime.strptime(date_str, "%Y-%m-%d")
            years_old = (datetime.now() - doc_date).days / 365.25

            # 최근 1년: +5점, 2년: +3점, 3년 이상: 0점
            if years_old < 1:
                return 5.0
            elif years_old < 2:
                return 3.0
            return 0.0
        except Exception as e:
            # 파싱 실패 시 보너스 없음 (로그는 디버그용만)
            logger.debug(f"날짜 파싱 실패 ({date_str}): {e}")
            return 0.0

    def apply_filename_similarity_bonus(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """파일명 유사도에 따라 점수 보너스 적용

        Args:
            query: 사용자 검색 질의
            results: 검색 결과 리스트

        Returns:
            보너스가 적용된 검색 결과 리스트
        """
        # 쿼리 정규화
        query_normalized = re.sub(r"[^\w\s]", " ", query.lower())
        query_tokens = set(query_normalized.split())

        if not query_tokens:
            return results

        for result in results:
            filename = result.get("filename", "")
            if not filename:
                continue

            # 파일명 정규화
            filename_clean = self._normalize_filename(filename)
            filename_tokens = set(filename_clean.split())

            if not filename_tokens:
                continue

            # Jaccard 유사도 계산
            intersection = query_tokens & filename_tokens
            union = query_tokens | filename_tokens
            jaccard_score = len(intersection) / len(union) if union else 0.0

            # 쿼리 커버리지 계산
            query_coverage = len(intersection) / len(query_tokens) if query_tokens else 0.0

            # 최종 유사도
            similarity = max(jaccard_score, query_coverage)

            # 보너스 적용
            bonus = self._get_similarity_bonus(similarity)
            if bonus > 0:
                original_score = result["score"]
                result["score"] += bonus
                logger.info(
                    f"📈 파일명 보너스: {filename[:40]} | "
                    f"유사도={similarity:.2f} | "
                    f"점수 {original_score:.2f} → {result['score']:.2f} (+{bonus:.1f})"
                )

        return results

    def _normalize_filename(self, filename: str) -> str:
        """파일명 정규화"""
        # 1. 날짜 패턴 제거
        filename_clean = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", filename)
        # 2. 확장자 제거
        filename_clean = re.sub(r"\.\w+$", "", filename_clean)
        # 3. 구분자 → 공백
        filename_clean = filename_clean.replace("_", " ")
        # 4. 특수문자 제거
        filename_clean = re.sub(r"[^\w\s]", " ", filename_clean.lower())
        return filename_clean

    def _get_similarity_bonus(self, similarity: float) -> float:
        """유사도 기반 보너스 반환"""
        if similarity >= self.config.HIGH_SIM_THRESHOLD:
            return self.config.HIGH_SIM_BONUS
        elif similarity >= self.config.MED_SIM_THRESHOLD:
            return self.config.MED_SIM_BONUS
        elif similarity >= self.config.LOW_SIM_THRESHOLD:
            return self.config.LOW_SIM_BONUS
        return 0.0

    def rescore_results(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """검색 결과 재스코어링

        Args:
            query: 검색 질의
            results: 검색 결과 리스트

        Returns:
            재스코어링된 결과 리스트 (점수 내림차순 정렬)
        """
        for result in results:
            result["score"] = self.calculate_relevance_score(query, result)

        # 점수 기준 정렬
        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        if results:
            logger.info(f"🔄 재스코어링 완료 (top score: {results[0]['score']:.2f})")

        return results


# 싱글톤 인스턴스
_scorer_instance: RelevanceScorer | None = None


def get_relevance_scorer() -> RelevanceScorer:
    """RelevanceScorer 싱글톤 인스턴스 반환"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = RelevanceScorer()
    return _scorer_instance
