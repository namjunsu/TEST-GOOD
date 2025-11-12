#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Query Parsing with Closed-World Validation (Hardened)
- Drafter: Closed-world exact → normalized-exact → fuzzy (guarded)
- Year: single/range/two-digit/relative terms with bounds
- Robust normalization (NFKC, role/honorific stripping)
- Token-pattern first, then CW pipeline with clear provenance
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "filters.yaml"

# -------------------------
# 정규식(사전 컴파일)
# -------------------------
RE_YEAR_4 = re.compile(r"(?<!\d)(19|20)\d{2}(?= *년| *년도|\b|[^0-9])")
RE_YEAR_2 = re.compile(r"(?<!\d)(\d{2})(?= *년| *년도|\b)")
RE_YEAR_RANGE = re.compile(
    r"(?<!\d)((?:19|20)\d{2}|\d{2})\s*(?:~|~?부터|[-–—]|~?→|~?to|~?>)\s*((?:19|20)\d{2}|\d{2})(?= *년| *년도|\b)?"
)
RE_RELATIVE = re.compile(r"(올해|작년|재작년)")
RE_KOREAN_NAME_2_4 = re.compile(r"[가-힣]{2,4}")
RE_ROLE_SUFFIX = re.compile(r"(과장|차장|부장|팀장|실장|국장|본부장|매니저|대리|사원|담당|선임|책임)\s*")
RE_PAREN = re.compile(r"[\(\)\[\]{}]")
RE_MULTI_SP = re.compile(r"\s+")
RE_TOKEN_DIRECTIVES = {
    "year": re.compile(r"year\s*[:=]\s*(\d{2,4})", re.IGNORECASE),
    "drafter": re.compile(r"drafter\s*[:=]\s*([A-Za-z가-힣 ]{2,30})", re.IGNORECASE),
}


# -------------------------
# 설정 로드 유틸
# -------------------------
def _load_yaml_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg
    except Exception as e:
        logger.warning(f"filters.yaml 로드 실패: {e}")
    return {}


def _normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def _normalize_name(s: str) -> str:
    # 괄호 제거, 공백 정리, 직함 제거, 영문 소문자화
    s = _normalize_text(RE_PAREN.sub("", s))
    s = s.replace(" ", "")
    s = RE_ROLE_SUFFIX.sub("", s)
    return s.lower()


def _jamo_approx(s: str) -> str:
    # 초간단 자모 근사: NFKD 후 자모만 보존
    decomp = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in decomp if 0x1100 <= ord(ch) <= 0x11FF)


def _sequence_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _two_digit_to_four(yy: int, today: date) -> int:
    # '24 → 2024 해석: 현재 세기 기준, +/- 20년 윈도우
    century = today.year // 100 * 100
    cand = century + yy
    if cand > today.year + 20:
        cand -= 100
    elif cand < 1900:
        cand += 100
    return cand


# -------------------------
# 데이터 구조
# -------------------------
@dataclass(frozen=True)
class ParseResult:
    year: Optional[str]
    drafter: Optional[str]
    source: Optional[str]  # 'token'|'closed_world'|'fuzzy'|None


# -------------------------
# 본체
# -------------------------
class QueryParser:
    """쿼리 파서 - Closed-World Validation + 연도 파서 고도화"""

    def __init__(self, known_drafters: Set[str], today: Optional[date] = None):
        """
        Args:
            known_drafters: 메타DB에서 로드한 '기안자 원형' 집합 (예: {'남준수','최새름',...})
            today: 상대 연도 해석 기준일 (테스트 용이성)
        """
        self.cfg = _load_yaml_config()
        self.stopwords = self._load_stopwords()
        self.token_patterns = self._load_token_patterns()
        self.today = today or date.today()

        # Closed-World 인덱스
        original = {d for d in (known_drafters or set()) if d and isinstance(d, str)}
        norm_pairs = {d: _normalize_name(d) for d in original}
        # 역인덱스(정규화값 → 원형 다중 매핑 방지: 가장 긴 원형 우선)
        rev: Dict[str, str] = {}
        for raw, norm in norm_pairs.items():
            keep = rev.get(norm)
            if keep is None or len(raw) > len(keep):
                rev[norm] = raw

        self._known_original: Set[str] = original
        self._known_norm_set: Set[str] = set(rev.keys())
        self._norm_to_original: Dict[str, str] = rev

        logger.info(
            f"✅ QueryParser 초기화: 기안자 {len(self._known_original)}명 "
            f"(정규화 {len(self._known_norm_set)}), 불용어 {len(self.stopwords)}개"
        )

    # ---------- 설정 ----------
    def _load_stopwords(self) -> Set[str]:
        sw = set(map(_normalize_text, self.cfg.get("drafter_stopwords", []) or []))
        if not sw:
            sw = {"문서", "자료", "파일", "보고서", "전체", "모든"}
        return sw

    def _load_token_patterns(self) -> Dict[str, str]:
        return self.cfg.get("query_tokens", {}) or {}

    # ---------- Public API ----------
    def parse_filters(self, query: str) -> Dict[str, Optional[str]]:
        """
        Returns: {"year": str|None, "drafter": str|None, "source": str|None}
        우선순위: 토큰 규칙 → (연도) → CW/퍼지 기안자
        """
        q = _normalize_text(query)

        # 1) 토큰 규칙 우선
        token_res = self._extract_from_tokens(q)
        if token_res["year"] or token_res["drafter"]:
            token_res["source"] = "token"
            logger.info(f"🎯 토큰 파싱: year={token_res['year']}, drafter={token_res['drafter']}")
            return token_res

        # 2) 연도
        year = self._extract_year(q)

        # 3) 기안자 (CW → 정규화-CW → 퍼지)
        drafter, source = self._extract_drafter_closed_world(q)

        result = {"year": year, "drafter": drafter, "source": source}
        logger.info(f"📋 파싱 결과: year={year}, drafter={drafter}, source={source}")
        return result

    # ---------- Token rules ----------
    def _extract_from_tokens(self, q: str) -> Dict[str, Optional[str]]:
        res = {"year": None, "drafter": None}

        # year
        pat_y = self.token_patterns.get("year")
        if pat_y:
            m = re.search(pat_y, q, re.IGNORECASE)
        else:
            m = RE_TOKEN_DIRECTIVES["year"].search(q)
        if m:
            y = m.group(1)
            if len(y) == 2:
                y4 = _two_digit_to_four(int(y), self.today)
                res["year"] = str(y4)
            elif len(y) == 4 and 1900 <= int(y) <= 2100:
                res["year"] = y

        # drafter
        pat_d = self.token_patterns.get("drafter")
        if pat_d:
            m = re.search(pat_d, q, re.IGNORECASE)
        else:
            m = RE_TOKEN_DIRECTIVES["drafter"].search(q)
        if m:
            cand_raw = m.group(1).strip()
            cand_norm = _normalize_name(cand_raw)
            if cand_norm in self._known_norm_set:
                res["drafter"] = self._norm_to_original[cand_norm]
        return res

    # ---------- Year ----------
    def _extract_year(self, q: str) -> Optional[str]:
        # 상대 표현
        rel = RE_RELATIVE.search(q)
        if rel:
            term = rel.group(1)
            if term == "올해":
                return str(self.today.year)
            if term == "작년":
                return str(self.today.year - 1)
            if term == "재작년":
                return str(self.today.year - 2)

        # 범위(우측 우선): "2023~25", "'24-'25", "2024-2025"
        m = RE_YEAR_RANGE.search(q)
        if m:
            a, b = m.group(1), m.group(2)
            y1 = int(a) if len(a) == 4 else _two_digit_to_four(int(a), self.today)
            y2 = int(b) if len(b) == 4 else _two_digit_to_four(int(b), self.today)
            y1, y2 = min(y1, y2), max(y1, y2)
            if 1900 <= y1 <= 2100 and 1900 <= y2 <= 2100:
                return f"{y1}-{y2}"

        # 단일 4자리
        m = RE_YEAR_4.search(q)
        if m:
            y = int(m.group(0))
            if 1900 <= y <= 2100:
                return str(y)

        # 단일 2자리
        m = RE_YEAR_2.search(q)
        if m:
            y4 = _two_digit_to_four(int(m.group(1)), self.today)
            if 1900 <= y4 <= 2100:
                return str(y4)

        return None

    # ---------- Drafter (CW → fuzzy) ----------
    def _extract_drafter_closed_world(self, q: str) -> Tuple[Optional[str], Optional[str]]:
        # 후보 추출: 한글 2-4자 + 공백 포함된 패턴도 추출
        candidates_ko = RE_KOREAN_NAME_2_4.findall(q)

        # 공백 포함 한글 패턴 추가 (예: "최 새 름", "남 준수")
        # 패턴: 1-2자 음절이 공백으로 구분되어 2-4개 있는 경우
        spaced_pattern = re.compile(r'[가-힣]{1,2}(?: +[가-힣]{1,2}){1,3}')
        candidates_spaced = spaced_pattern.findall(q)

        # 공백 포함 후보에서 불용어 제거 (단어 단위)
        def remove_stopwords(s: str) -> str:
            words = s.split()
            filtered = [w for w in words if _normalize_text(w) not in self.stopwords]
            return " ".join(filtered) if filtered else ""

        candidates_spaced = [remove_stopwords(c) for c in candidates_spaced]
        # 빈 문자열 제거 + 공백 제거 후 길이가 2-4자인 것만 유지
        candidates_spaced = [c for c in candidates_spaced if c and 2 <= len(c.replace(" ", "")) <= 4]

        # 모든 후보 합치기
        all_candidates = candidates_ko + candidates_spaced

        # 직함 제거/정규화
        cand_norm = [_normalize_name(c) for c in all_candidates if _normalize_text(c) not in self.stopwords]
        # 빈 값 제거 및 길이 체크 (한국 이름은 보통 2-4자)
        cand_norm = [c for c in cand_norm if c and 2 <= len(c) <= 4]

        if not cand_norm:
            return None, None

        # 1) 정규화-Closed World
        for n in cand_norm:
            if n in self._known_norm_set:
                return self._norm_to_original[n], "closed_world"

        # 2) 퍼지 매칭(안전장치 포함)
        best: Tuple[Optional[str], float] = (None, 0.0)
        # 후보·대상 상한
        max_checks = 50
        checked = 0
        for n in cand_norm:
            nj = _jamo_approx(n)
            for k in self._known_norm_set:
                if checked >= max_checks:
                    break
                # 길이 차 과도 시 skip
                if abs(len(n) - len(k)) > 1:
                    checked += 1
                    continue
                kj = _jamo_approx(k)
                # 자모 근접성 1차 컷
                if _sequence_ratio(nj, kj) < 0.80:
                    checked += 1
                    continue
                # 원문 근접성(가중)
                score = 0.5 * _sequence_ratio(n, k) + 0.5 * _sequence_ratio(nj, kj)
                if score > best[1]:
                    best = (k, score)
                checked += 1

        if best[0] and best[1] >= 0.87:
            return self._norm_to_original[best[0]], "fuzzy"

        return None, None


# ---------- 함수형 API ----------
def parse_filters_simple(query: str, known_drafters: Set[str]) -> Dict[str, Optional[str]]:
    parser = QueryParser(known_drafters)
    return parser.parse_filters(query)
