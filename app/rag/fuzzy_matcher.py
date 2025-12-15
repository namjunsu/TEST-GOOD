"""퍼지 매칭 모듈

영문 브랜드/모델명의 다양한 표기 변형을 자동으로 매칭합니다.
- TVLogic, TV-Logic, TvLogic, Tv-Logic → 모두 같은 것으로 인식
- 하이픈, 대소문자, 띄어쓰기 변형 자동 처리

Usage:
    >>> from app.rag.fuzzy_matcher import fuzzy_expand_query
    >>> fuzzy_expand_query("TV-Logic", all_terms)
    ["TVLogic", "TvLogic", "Tv-Logic", "TV-Logic"]
"""

import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from app.core.logging import get_logger

logger = get_logger(__name__)

# 정규화: 하이픈, 공백 제거 + 소문자
def _normalize(text: str) -> str:
    """브랜드명 정규화 (비교용)"""
    return re.sub(r"[-_\s]", "", text).lower()


def _is_similar_brand(term1: str, term2: str, threshold: int = 85) -> bool:
    """두 브랜드명이 유사한지 판단

    정규화 후 비교하거나 퍼지 매칭으로 비교
    """
    norm1 = _normalize(term1)
    norm2 = _normalize(term2)

    # 정규화 후 완전 일치
    if norm1 == norm2:
        return True

    # 한쪽이 다른 쪽을 포함 (길이 차이가 작을 때만)
    if len(norm1) >= 3 and len(norm2) >= 3:
        if norm1 in norm2 or norm2 in norm1:
            len_ratio = min(len(norm1), len(norm2)) / max(len(norm1), len(norm2))
            if len_ratio > 0.7:
                return True

    # 퍼지 매칭 (ratio)
    score = fuzz.ratio(norm1, norm2)
    return score >= threshold


def fuzzy_find_variants(
    query_term: str,
    candidate_terms: list[str],
    threshold: int = 85,
    max_results: int = 10,
) -> list[str]:
    """쿼리 용어와 유사한 후보 용어들을 찾음

    Args:
        query_term: 검색어 (예: "티비로직", "TV-Logic")
        candidate_terms: 후보 용어 리스트 (DB의 모든 파일명에서 추출된 용어들)
        threshold: 유사도 임계값 (0-100)
        max_results: 최대 결과 수

    Returns:
        유사한 용어 리스트
    """
    if not query_term or not candidate_terms:
        return []

    query_norm = _normalize(query_term)
    results = []
    seen_normalized = {query_norm}

    for candidate in candidate_terms:
        cand_norm = _normalize(candidate)

        # 이미 본 정규화 형태는 스킵
        if cand_norm in seen_normalized:
            continue

        if _is_similar_brand(query_term, candidate, threshold):
            results.append(candidate)
            seen_normalized.add(cand_norm)

            if len(results) >= max_results:
                break

    return results


class BrandVariantMatcher:
    """파일명에서 추출한 브랜드/모델명 변형 매처

    DB의 모든 파일명을 분석하여 브랜드명 변형을 자동으로 찾습니다.
    """

    def __init__(self):
        self._brand_terms: set[str] = set()
        self._normalized_to_variants: dict[str, list[str]] = {}
        self._loaded = False

    def load_from_filenames(self, filenames: list[str]) -> None:
        """파일명 리스트에서 브랜드/모델명 추출"""
        brand_pattern = re.compile(
            r"[A-Z][a-z]+[A-Z][a-zA-Z]*"  # CamelCase: TVLogic, BlackMagic
            r"|[A-Z]{2,}[-]?[A-Z]*[a-z]*"  # 대문자: SDI, HD-SDI
            r"|[A-Z][a-z]+[-][A-Z][a-z]+"  # 하이픈: Tv-Logic
            r"|[A-Za-z]+[-]?\d+[A-Za-z]*"  # 모델명: EX-3, PMW500
        )

        for filename in filenames:
            # 확장자 제거, 언더스코어를 공백으로
            name = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
            name = name.replace("_", " ")

            # 패턴 매칭
            matches = brand_pattern.findall(name)
            for match in matches:
                if len(match) >= 2:  # 최소 2글자
                    self._brand_terms.add(match)

        # 정규화된 형태로 그룹화
        for term in self._brand_terms:
            norm = _normalize(term)
            if norm not in self._normalized_to_variants:
                self._normalized_to_variants[norm] = []
            if term not in self._normalized_to_variants[norm]:
                self._normalized_to_variants[norm].append(term)

        self._loaded = True
        logger.info(f"✅ 브랜드 매처 로드: {len(self._brand_terms)}개 용어, {len(self._normalized_to_variants)}개 그룹")

    def get_variants(self, term: str) -> list[str]:
        """주어진 용어의 모든 변형을 반환

        Args:
            term: 검색어 (예: "TVLogic")

        Returns:
            변형 리스트 (예: ["TVLogic", "TvLogic", "TV-Logic"])
        """
        if not self._loaded:
            return [term]

        norm = _normalize(term)

        # 정확히 일치하는 그룹이 있으면 반환
        if norm in self._normalized_to_variants:
            return self._normalized_to_variants[norm]

        # 퍼지 매칭으로 유사한 그룹 찾기
        for group_norm, variants in self._normalized_to_variants.items():
            if _is_similar_brand(term, variants[0] if variants else "", threshold=80):
                return variants

        return [term]

    def expand_query(self, query: str) -> str:
        """쿼리의 브랜드/모델명을 확장

        Args:
            query: 원본 쿼리 (예: "TV-Logic 모니터")

        Returns:
            확장된 쿼리 (예: "TV-Logic TVLogic TvLogic 모니터")
        """
        if not self._loaded:
            return query

        tokens = query.split()
        expanded_tokens = []
        seen = set()

        for token in tokens:
            # 영문 브랜드명 패턴인지 확인
            if re.match(r"^[A-Za-z].*[A-Za-z0-9]$", token) and len(token) >= 2:
                variants = self.get_variants(token)
                for v in variants:
                    if v.lower() not in seen:
                        expanded_tokens.append(v)
                        seen.add(v.lower())

            # 원본 토큰도 추가 (중복 제거)
            if token.lower() not in seen:
                expanded_tokens.append(token)
                seen.add(token.lower())

        return " ".join(expanded_tokens)


# 싱글톤 인스턴스
_matcher: BrandVariantMatcher | None = None


def get_brand_matcher() -> BrandVariantMatcher:
    """싱글톤 브랜드 매처 반환"""
    global _matcher
    if _matcher is None:
        _matcher = BrandVariantMatcher()
    return _matcher


def init_brand_matcher_from_db(db_path: str = "metadata.db") -> BrandVariantMatcher:
    """DB에서 파일명을 로드하여 브랜드 매처 초기화

    Args:
        db_path: SQLite DB 경로

    Returns:
        초기화된 BrandVariantMatcher
    """
    import sqlite3
    from pathlib import Path

    matcher = get_brand_matcher()

    if matcher._loaded:
        return matcher

    db_file = Path(db_path)
    if not db_file.exists():
        logger.warning(f"⚠️ DB 파일 없음: {db_path}, 빈 매처 사용")
        return matcher

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT filename FROM documents")
        filenames = [row[0] for row in cursor.fetchall()]
        conn.close()

        matcher.load_from_filenames(filenames)
        logger.info(f"✅ DB에서 브랜드 매처 초기화 완료: {len(filenames)}개 파일")

    except Exception as e:
        logger.error(f"❌ 브랜드 매처 초기화 실패: {e}")

    return matcher


def fuzzy_expand_query(query: str, db_path: str = "metadata.db") -> str:
    """쿼리를 퍼지 매칭으로 확장 (편의 함수)

    Args:
        query: 원본 쿼리
        db_path: DB 경로

    Returns:
        확장된 쿼리

    Example:
        >>> fuzzy_expand_query("TV-Logic 모니터")
        "TV-Logic TVLogic TvLogic Tv-Logic 모니터"
    """
    matcher = init_brand_matcher_from_db(db_path)
    return matcher.expand_query(query)
