"""
앵커 스코어링 v1.0
===================

프로파일별 앵커 점수 계산:
- allow 필터 (필수)
- deny 패널티
- boost 가중 (high/medium/vendor)
- proximity 보너스 (키워드 간 거리)
"""

import re
import unicodedata
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# 한글 경계 매크로
KBL = r"(?<![가-힣A-Za-z0-9])"
KBR = r"(?![가-힣A-Za-z0-9])"


class AnchorScorer:
    """프로파일별 앵커 점수 계산"""

    def __init__(self, config_path: str = "config/router_keywords.yaml"):
        """
        Args:
            config_path: 라우터 키워드 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.profiles = self._compile_profiles()

        # 메트릭 수집
        self.metrics = {
            "total_scored": 0,
            "by_profile": {},
            "denies": 0,
            "low_confidence": 0,
        }

        logger.info(f"앵커 스코어 초기화: {len(self.profiles)} 프로파일 컴파일")

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"⚠️ 설정 로드 실패: {e}, 기본값 사용")
            return {}

    def _expand_macro(self, pattern: str) -> str:
        """
        {KBL}/{KBR} 매크로 확장

        Args:
            pattern: 원본 패턴

        Returns:
            확장된 패턴
        """
        pattern = pattern.replace("{KBL}", KBL)
        pattern = pattern.replace("{KBR}", KBR)
        return pattern

    def _compile_profiles(self) -> Dict[str, Dict[str, Any]]:
        """프로파일별 패턴 컴파일"""
        compiled = {}
        profiles_raw = self.config.get("doc_anchored", {}).get("profiles", {})

        for profile_name, profile_config in profiles_raw.items():
            compiled[profile_name] = {
                "description": profile_config.get("description", ""),
                "allow": self._compile_patterns(profile_config.get("allow", [])),
                "deny": self._compile_patterns(profile_config.get("deny", [])),
                "boost_high": self._compile_patterns(
                    profile_config.get("boost", {}).get("high", [])
                ),
                "boost_medium": self._compile_patterns(
                    profile_config.get("boost", {}).get("medium", [])
                ),
                "boost_vendor": self._compile_patterns(
                    profile_config.get("boost", {}).get("vendor", [])
                ),
                "weights": profile_config.get(
                    "weights", {"high": 3.0, "medium": 1.5, "vendor": 1.0}
                ),
                "deny_penalty": profile_config.get("deny_penalty", -4.0),
                "pass_threshold": profile_config.get("pass_threshold", 1.0),
                "proximity_pairs": profile_config.get("proximity_pairs", []),
            }

        return compiled

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """패턴 리스트 컴파일"""
        compiled = []
        for pattern in patterns:
            try:
                expanded = self._expand_macro(pattern)
                compiled.append(re.compile(expanded, re.IGNORECASE))
            except Exception as e:
                logger.warning(f"⚠️ 패턴 컴파일 실패: {pattern} - {e}")
        return compiled

    def normalize_text(self, text: str) -> str:
        """
        텍스트 정규화

        Args:
            text: 원본 텍스트

        Returns:
            정규화된 텍스트
        """
        # NFKC 정규화
        text = unicodedata.normalize("NFKC", text)

        # 하이픈 통일
        text = re.sub(r"[‐‑‒–—―−]", "-", text)

        # 공백 압축
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _check_allow(
        self, text: str, patterns: List[re.Pattern]
    ) -> Tuple[bool, List[str]]:
        """
        allow 패턴 체크 (하나라도 매칭 필수)

        Args:
            text: 대상 텍스트
            patterns: allow 패턴 리스트

        Returns:
            (매칭 여부, 매칭된 패턴 리스트)
        """
        matched = []
        for pattern in patterns:
            if pattern.search(text):
                matched.append(pattern.pattern)

        return (len(matched) > 0, matched)

    def _check_deny(
        self, text: str, patterns: List[re.Pattern]
    ) -> Tuple[bool, List[str]]:
        """
        deny 패턴 체크

        Args:
            text: 대상 텍스트
            patterns: deny 패턴 리스트

        Returns:
            (매칭 여부, 매칭된 패턴 리스트)
        """
        matched = []
        for pattern in patterns:
            if pattern.search(text):
                matched.append(pattern.pattern)

        return (len(matched) > 0, matched)

    def _calculate_boost(
        self,
        text: str,
        high: List[re.Pattern],
        medium: List[re.Pattern],
        vendor: List[re.Pattern],
        weights: Dict[str, float],
    ) -> float:
        """
        boost 점수 계산 (high/medium/vendor 누적)

        Args:
            text: 대상 텍스트
            high: high boost 패턴
            medium: medium boost 패턴
            vendor: vendor boost 패턴
            weights: 가중치

        Returns:
            boost 점수
        """
        score = 0.0

        for pattern in high:
            if pattern.search(text):
                score += weights.get("high", 3.0)

        for pattern in medium:
            if pattern.search(text):
                score += weights.get("medium", 1.5)

        for pattern in vendor:
            if pattern.search(text):
                score += weights.get("vendor", 1.0)

        return score

    def _calculate_proximity(
        self, text: str, pairs: List[Dict[str, Any]]
    ) -> float:
        """
        proximity 보너스 계산 (키워드 간 거리)

        Args:
            text: 대상 텍스트
            pairs: proximity 설정 리스트

        Returns:
            proximity 보너스 점수
        """
        bonus = 0.0

        for pair in pairs:
            pattern_a = self._expand_macro(pair["a"])
            pattern_b = self._expand_macro(pair["b"])
            window = pair.get("window", 40)
            bonus_value = pair.get("bonus", 1.0)

            # 패턴 A 찾기
            matches_a = list(re.finditer(pattern_a, text, re.IGNORECASE))
            matches_b = list(re.finditer(pattern_b, text, re.IGNORECASE))

            # A와 B 간 거리 체크
            for match_a in matches_a:
                for match_b in matches_b:
                    distance = abs(match_a.start() - match_b.start())
                    if distance <= window:
                        bonus += bonus_value
                        break  # 한 쌍당 한 번만 보너스

        return bonus

    def score_document(
        self, text: str, profile_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        문서에 대해 프로파일별 앵커 점수 계산

        Args:
            text: 문서 텍스트 (snippet + doc_id 등)
            profile_name: 프로파일 이름

        Returns:
            {
                "profile": str,
                "score": float,
                "pass": bool,
                "details": {
                    "allow_matched": list,
                    "deny_matched": list,
                    "boost_score": float,
                    "proximity_bonus": float,
                }
            }
            또는 None (프로파일 없음)
        """
        if profile_name not in self.profiles:
            logger.warning(f"⚠️ 프로파일 없음: {profile_name}")
            return None

        profile = self.profiles[profile_name]
        text_norm = self.normalize_text(text)

        # 1. allow 체크 (필수)
        allow_pass, allow_matched = self._check_allow(text_norm, profile["allow"])
        if not allow_pass:
            return {
                "profile": profile_name,
                "score": 0.0,
                "pass": False,
                "details": {
                    "allow_matched": [],
                    "deny_matched": [],
                    "boost_score": 0.0,
                    "proximity_bonus": 0.0,
                    "reason": "allow_filter_failed",
                },
            }

        # 2. deny 체크 (패널티)
        deny_hit, deny_matched = self._check_deny(text_norm, profile["deny"])
        deny_score = profile["deny_penalty"] if deny_hit else 0.0

        # 3. boost 점수
        boost_score = self._calculate_boost(
            text_norm,
            profile["boost_high"],
            profile["boost_medium"],
            profile["boost_vendor"],
            profile["weights"],
        )

        # 4. proximity 보너스
        proximity_bonus = self._calculate_proximity(
            text_norm, profile["proximity_pairs"]
        )

        # 5. 최종 점수
        total_score = boost_score + proximity_bonus + deny_score

        # 6. pass 여부
        pass_threshold = profile["pass_threshold"]
        passed = total_score >= pass_threshold

        # 메트릭 수집
        self.metrics["total_scored"] += 1
        if profile_name not in self.metrics["by_profile"]:
            self.metrics["by_profile"][profile_name] = 0
        self.metrics["by_profile"][profile_name] += 1
        if deny_hit:
            self.metrics["denies"] += 1
        if total_score < 0.3:
            self.metrics["low_confidence"] += 1

        return {
            "profile": profile_name,
            "score": total_score,
            "pass": passed,
            "details": {
                "allow_matched": allow_matched,
                "deny_matched": deny_matched,
                "boost_score": boost_score,
                "proximity_bonus": proximity_bonus,
                "deny_penalty": deny_score,
            },
        }

    def get_metrics(self) -> Dict[str, Any]:
        """메트릭 반환"""
        return self.metrics.copy()


# 싱글톤 인스턴스
_scorer = None


def get_anchor_scorer() -> AnchorScorer:
    """앵커 스코어 싱글톤 반환"""
    global _scorer
    if _scorer is None:
        _scorer = AnchorScorer()
    return _scorer
