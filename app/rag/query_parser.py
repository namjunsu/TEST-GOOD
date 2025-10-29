"""
쿼리 파싱 모듈 - Closed-World Validation
기안자/연도 추출을 메타데이터 DB 기반으로 검증
"""

import re
import yaml
from pathlib import Path
from typing import Optional, Dict, Set
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)

# 설정 로드
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "filters.yaml"


class QueryParser:
    """쿼리 파서 - Closed-World Validation 적용"""

    def __init__(self, known_drafters: Set[str]):
        """
        Args:
            known_drafters: DB에서 로드한 고유 기안자 집합
        """
        self.known_drafters = known_drafters
        self.stopwords = self._load_stopwords()
        self.token_patterns = self._load_token_patterns()

        logger.info(f"✅ QueryParser 초기화: {len(known_drafters)}명 기안자, {len(self.stopwords)}개 불용어")

    def _load_stopwords(self) -> Set[str]:
        """불용어 로드"""
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return set(config.get('drafter_stopwords', []))
        except Exception as e:
            logger.warning(f"불용어 로드 실패, 기본값 사용: {e}")
            return {'문서', '자료', '파일', '보고서', '전체', '모든'}

    def _load_token_patterns(self) -> Dict[str, str]:
        """토큰 패턴 로드"""
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('query_tokens', {})
        except Exception as e:
            logger.warning(f"토큰 패턴 로드 실패: {e}")
            return {}

    def parse_filters(self, query: str) -> Dict[str, Optional[str]]:
        """쿼리에서 필터 추출 (우선순위: 토큰 > Closed-World > 패턴)

        Args:
            query: 사용자 질의

        Returns:
            dict: {"year": str, "drafter": str, "source": str}
        """
        result = {
            "year": None,
            "drafter": None,
            "source": None
        }

        # 1단계: 토큰 패턴 우선 추출
        token_result = self._extract_from_tokens(query)
        if token_result['year'] or token_result['drafter']:
            result.update(token_result)
            result['source'] = 'token'
            logger.info(f"🎯 토큰 파싱: year={result['year']}, drafter={result['drafter']}")
            return result

        # 2단계: 연도 추출
        result['year'] = self._extract_year(query)

        # 3단계: 기안자 추출 (Closed-World Validation)
        drafter, source = self._extract_drafter_closed_world(query)
        result['drafter'] = drafter
        result['source'] = source

        logger.info(f"📋 파싱 결과: year={result['year']}, drafter={result['drafter']}, source={result['source']}")
        return result

    def _extract_from_tokens(self, query: str) -> Dict[str, Optional[str]]:
        """토큰 문법 추출 (year:2024, drafter:최새름)"""
        result = {"year": None, "drafter": None}

        # year: 토큰
        if 'year' in self.token_patterns:
            match = re.search(self.token_patterns['year'], query, re.IGNORECASE)
            if match:
                result['year'] = match.group(1)

        # drafter: 토큰
        if 'drafter' in self.token_patterns:
            match = re.search(self.token_patterns['drafter'], query, re.IGNORECASE)
            if match:
                drafter_raw = match.group(1).strip()
                # 공백 정규화
                drafter_normalized = self._normalize_name(drafter_raw)
                if drafter_normalized in self.known_drafters:
                    result['drafter'] = drafter_normalized

        return result

    def _extract_year(self, query: str) -> Optional[str]:
        """연도 추출"""
        match = re.search(r'(\d{4})년?', query)
        return match.group(1) if match else None

    def _extract_drafter_closed_world(self, query: str) -> tuple[Optional[str], str]:
        """기안자 추출 - Closed-World Validation

        Returns:
            (drafter, source): (기안자명, 출처: 'closed_world'|'fuzzy'|None)
        """
        # 1. 한글 2-4자 토큰 후보 추출
        candidates = re.findall(r'[가-힣]{2,4}', query)

        # 2. 불용어 제거
        candidates = [c for c in candidates if c not in self.stopwords]

        if not candidates:
            return None, None

        # 3. Exact Match (닫힌 집합 검증)
        for candidate in candidates:
            if candidate in self.known_drafters:
                logger.info(f"✅ 기안자 정확 매칭: {candidate}")
                return candidate, 'closed_world'

        # 4. Fuzzy Match (편집 거리 기반, 공백 정규화)
        for candidate in candidates:
            normalized = self._normalize_name(candidate)
            if normalized in self.known_drafters:
                logger.info(f"✅ 기안자 정규화 매칭: {candidate} → {normalized}")
                return normalized, 'closed_world'

            # 유사도 매칭 (threshold = 0.85)
            match = self._fuzzy_match(normalized, self.known_drafters, threshold=0.85)
            if match:
                logger.info(f"✅ 기안자 유사도 매칭: {candidate} → {match}")
                return match, 'fuzzy'

        # 5. 매칭 실패
        logger.info(f"⚠️ 기안자 후보 '{candidates}'는 KNOWN_DRAFTERS에 없음 → None")
        return None, None

    def _normalize_name(self, name: str) -> str:
        """이름 정규화 (공백 제거, 영문 소문자화)"""
        # 공백 제거
        name = name.replace(' ', '')
        # 영문 소문자화
        return name.lower()

    def _fuzzy_match(self, query: str, candidates: Set[str], threshold: float = 0.85) -> Optional[str]:
        """유사도 기반 매칭

        Args:
            query: 검색 문자열
            candidates: 후보 집합
            threshold: 유사도 임계값 (0.0-1.0)

        Returns:
            가장 유사한 후보 또는 None
        """
        best_match = None
        best_score = 0.0

        query_normalized = self._normalize_name(query)

        for candidate in candidates:
            candidate_normalized = self._normalize_name(candidate)
            score = SequenceMatcher(None, query_normalized, candidate_normalized).ratio()

            if score > best_score and score >= threshold:
                best_score = score
                best_match = candidate

        return best_match


def parse_filters_simple(query: str, known_drafters: Set[str]) -> Dict[str, Optional[str]]:
    """간단한 파싱 함수 (함수형 API)

    Args:
        query: 사용자 질의
        known_drafters: 고유 기안자 집합

    Returns:
        {"year": str, "drafter": str, "source": str}
    """
    parser = QueryParser(known_drafters)
    return parser.parse_filters(query)