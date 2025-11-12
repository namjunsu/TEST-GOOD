"""
쿼리 필터링 v1.1
==================

토큰 경계 보장 + 상대 시간 전처리 + 도메인 용어 보호
"""

import re
import unicodedata
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from app.core.logging import get_logger

logger = get_logger(__name__)

# 정규식 토큰 경계
TOKEN = r"(?:^|(?<=\W))"  # 앞 경계
ETOKEN = r"(?:(?=\W)|$)"  # 뒤 경계


class QueryFilter:
    """쿼리 필터링 및 전처리 파이프라인"""

    def __init__(self, config_path: str = "config/filters.yaml"):
        """
        Args:
            config_path: 필터 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()

        # 불용어 정규식 컴파일
        drafter_cfg = self.config.get("drafter_stopwords", {})
        search_cfg = self.config.get("search_stopwords", {})

        self.drafter_sw_re = self._build_stopword_regex(
            drafter_cfg.get("values", [])
        )
        self.search_sw_re = self._build_stopword_regex(search_cfg.get("values", []))

        # 상대 연도 용어
        self.relative_year_terms = drafter_cfg.get("relative_year_terms", [])

        # 숫자 접미어 보호 패턴
        preserve_units = search_cfg.get("preserve_numeric_suffixed_units", [])
        self.preserve_numeric_re = self._build_numeric_preserve_regex(preserve_units)

        # 쿼리 토큰 패턴 (확장)
        self.query_tokens = self._compile_query_tokens(
            self.config.get("query_tokens", {})
        )

        # 도메인 용어 (변형 생성)
        self.domain_terms = self._build_domain_terms(
            self.config.get("domain_terms", {})
        )

        logger.info(
            f"쿼리 필터 초기화: drafter_sw={len(drafter_cfg.get('values', []))}, "
            f"search_sw={len(search_cfg.get('values', []))}, "
            f"domain_terms={len(self.domain_terms)}"
        )

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"⚠️ 설정 로드 실패: {e}, 기본값 사용")
            return {}

    def _build_stopword_regex(self, words: List[str]) -> re.Pattern:
        """불용어 리스트 → 토큰 경계 정규식 (NFKC 정규화)"""
        # NFKC 정규화 + 중복 제거
        norm = sorted(
            {unicodedata.normalize("NFKC", w).strip() for w in words if w}
        )
        # 길이 긴 것 우선 (부분 겹침 방지), 특수문자 이스케이프
        pat = "|".join(sorted(map(re.escape, norm), key=len, reverse=True))
        if not pat:
            # 빈 패턴 방지 (매칭 없음)
            return re.compile(r"(?!.*)", re.IGNORECASE)
        return re.compile(f"{TOKEN}(?:{pat}){ETOKEN}", re.IGNORECASE)

    def _build_numeric_preserve_regex(self, units: List[str]) -> Optional[re.Pattern]:
        """숫자 접미어 보호 패턴 (예: 12건)"""
        if not units:
            return None
        # \d+\s*건 형태를 보호
        pat = "|".join(map(re.escape, units))
        return re.compile(rf"\d+\s*(?:{pat})\b", re.IGNORECASE)

    def _compile_query_tokens(self, tokens: Dict[str, str]) -> Dict[str, re.Pattern]:
        """쿼리 토큰 패턴 컴파일"""
        compiled = {}
        for name, pattern in tokens.items():
            try:
                compiled[name] = re.compile(pattern, re.IGNORECASE)
            except Exception as e:
                logger.warning(f"⚠️ 토큰 패턴 컴파일 실패 ({name}): {e}")
        return compiled

    def _build_domain_terms(self, config: Dict[str, Any]) -> Set[str]:
        """도메인 용어 집합 생성 (변형 자동 생성)"""
        base = config.get("base", [])
        generate_variants = config.get("generate_variants", False)

        terms = set()
        for term in base:
            terms.add(term)
            if generate_variants:
                # 변형 생성 (하이픈/공백/무공백)
                variants = self._generate_term_variants(term)
                terms.update(variants)

        return terms

    def _generate_term_variants(self, term: str) -> Set[str]:
        """용어 변형 생성 (하이픈/공백/무공백)"""
        variants = {term}

        # 하이픈 → 공백
        if "-" in term:
            variants.add(term.replace("-", " "))
            # 하이픈 → 무공백
            variants.add(term.replace("-", ""))

        # 공백 → 무공백
        if " " in term:
            variants.add(term.replace(" ", ""))
            # 공백 → 하이픈
            variants.add(term.replace(" ", "-"))

        return variants

    def protect_domain_terms(self, query: str) -> Tuple[str, Dict[str, str]]:
        """도메인 용어를 일시 치환으로 보호 (불용어 필터 영향 배제)"""
        mapping = {}
        for i, term in enumerate(
            sorted(self.domain_terms, key=len, reverse=True), 1
        ):
            if term in query:
                key = f"__DOM_{i}__"
                query = query.replace(term, key)
                mapping[key] = term
        return query, mapping

    def restore_domain_terms(self, query: str, mapping: Dict[str, str]) -> str:
        """보호된 도메인 용어 복원"""
        for key, value in mapping.items():
            query = query.replace(key, value)
        return query

    def resolve_relative_year(self, token: str) -> Optional[Tuple[int, int]]:
        """상대 연도 → 절대 연도 범위 변환 (올해/작년/재작년)"""
        y = datetime.now().year
        token_lower = token.lower()
        if token_lower == "올해":
            return (y, y)
        if token_lower == "작년":
            return (y - 1, y - 1)
        if token_lower == "재작년":
            return (y - 2, y - 2)
        return None

    def parse_query_tokens(self, query: str) -> Dict[str, Any]:
        """쿼리 토큰 파싱 (year, drafter, type, date 등)"""
        parsed = {}

        # year 토큰 파싱 (범위/비교 연산 지원)
        if "year" in self.query_tokens:
            match = self.query_tokens["year"].search(query)
            if match:
                groups = match.groups()
                # 그룹 1,2: 범위 (2023~2025)
                # 그룹 3,4: 연산자 (>=2023)
                # 그룹 5: 단일 (2023)
                year_start = int(groups[0]) if groups[0] else None
                year_end = int(groups[1]) if groups[1] else None
                operator = groups[2] if groups[2] else None
                operand = int(groups[3]) if groups[3] else None
                single = int(groups[4]) if groups[4] else None

                if year_start and year_end:
                    # 범위 (2023~2025)
                    parsed["year"] = {"range": (year_start, year_end)}
                elif operator and operand:
                    # 비교 연산자 (>=2023 등)
                    parsed["year"] = {"operator": operator, "value": operand}
                elif single:
                    # 단일 연도
                    parsed["year"] = single

        # drafter 토큰 파싱 (따옴표/괄호 허용)
        if "drafter" in self.query_tokens:
            match = self.query_tokens["drafter"].search(query)
            if match:
                # 3개 그룹 중 매칭된 것 선택 (인용/단일인용/일반)
                groups = match.groups()
                drafter = groups[0] or groups[1] or groups[2]
                if drafter:
                    parsed["drafter"] = drafter.strip()

        # type 토큰 파싱
        if "type" in self.query_tokens:
            match = self.query_tokens["type"].search(query)
            if match:
                parsed["type"] = match.group(1)

        # date 토큰 파싱 (범위 지원)
        if "date" in self.query_tokens:
            match = self.query_tokens["date"].search(query)
            if match:
                groups = match.groups()
                date_start = groups[0] if groups[0] else None
                date_end = groups[1] if groups[1] else None

                if date_end:
                    parsed["date"] = {"range": (date_start, date_end)}
                else:
                    parsed["date"] = date_start

        return parsed

    def preprocess_query(self, query: str) -> Dict[str, Any]:
        """
        쿼리 전처리 파이프라인

        순서:
        1. NFKC 정규화
        2. 도메인 용어 보호 치환
        3. 상대 연도 해석
        4. 쿼리 토큰 파싱 (year, drafter, type, date)
        5. 불용어 제거 (토큰 경계 정규식)
        6. 도메인 용어 복원

        Returns:
            {
                "cleaned_query": str,
                "parsed_tokens": dict,
                "removed_stopwords": list,
                "protected_terms": list,
            }
        """
        original = query

        # 1. NFKC 정규화
        query = unicodedata.normalize("NFKC", query)

        # 2. 도메인 용어 보호
        query, domain_mapping = self.protect_domain_terms(query)
        protected_terms = list(domain_mapping.values())

        # 3. 상대 연도 해석 (상대 용어 → 절대 연도)
        for term in self.relative_year_terms:
            if term in query:
                year_range = self.resolve_relative_year(term)
                if year_range:
                    # "올해" → "year:2025" 형태로 치환
                    if year_range[0] == year_range[1]:
                        replacement = f"year:{year_range[0]}"
                    else:
                        replacement = f"year:{year_range[0]}~{year_range[1]}"
                    query = query.replace(term, replacement)
                    logger.debug(f"상대 연도 해석: '{term}' → '{replacement}'")

        # 4. 쿼리 토큰 파싱
        parsed_tokens = self.parse_query_tokens(query)

        # 5. 불용어 제거 (drafter stopwords + search stopwords)
        removed_stopwords = []

        # Drafter stopwords 제거
        matches = list(self.drafter_sw_re.finditer(query))
        for match in reversed(matches):
            removed_stopwords.append(match.group())
            query = query[: match.start()] + " " + query[match.end() :]

        # Search stopwords 제거 (숫자 접미어 보호)
        if self.preserve_numeric_re:
            # 숫자 접미어 보호 (예: 12건)
            numeric_matches = list(self.preserve_numeric_re.finditer(query))
            protected_spans = {(m.start(), m.end()) for m in numeric_matches}

            # Search stopwords 제거 (보호 범위 제외)
            matches = list(self.search_sw_re.finditer(query))
            for match in reversed(matches):
                # 보호 범위와 겹치지 않으면 제거
                if not any(
                    start <= match.start() < end or start < match.end() <= end
                    for start, end in protected_spans
                ):
                    removed_stopwords.append(match.group())
                    query = query[: match.start()] + " " + query[match.end() :]
        else:
            # 보호 없이 제거
            matches = list(self.search_sw_re.finditer(query))
            for match in reversed(matches):
                removed_stopwords.append(match.group())
                query = query[: match.start()] + " " + query[match.end() :]

        # 6. 도메인 용어 복원
        query = self.restore_domain_terms(query, domain_mapping)

        # 7. 공백 정리
        query = re.sub(r"\s+", " ", query).strip()

        logger.info(
            f"쿼리 전처리: '{original}' → '{query}' "
            f"(parsed={parsed_tokens}, removed={len(removed_stopwords)}, protected={len(protected_terms)})"
        )

        return {
            "cleaned_query": query,
            "parsed_tokens": parsed_tokens,
            "removed_stopwords": removed_stopwords,
            "protected_terms": protected_terms,
        }


# 싱글톤 인스턴스
_filter = None


def get_query_filter() -> QueryFilter:
    """쿼리 필터 싱글톤 반환"""
    global _filter
    if _filter is None:
        _filter = QueryFilter()
    return _filter
