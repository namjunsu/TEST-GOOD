"""
프로파일 매칭 v1.0
===================

쿼리에서 키워드 감지 → 프로파일 후보 선정
"""

import re
import unicodedata
import yaml
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# 한글 경계 매크로
KBL = r"(?<![가-힣A-Za-z0-9])"  # Korean Boundary Left
KBR = r"(?![가-힣A-Za-z0-9])"  # Korean Boundary Right


class ProfileMatcher:
    """쿼리 기반 프로파일 매칭"""

    def __init__(self, config_path: str = "config/router_keywords.yaml"):
        """
        Args:
            config_path: 라우터 키워드 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.profile_patterns = self._compile_profile_patterns()
        self.priority = self.config.get("profile_matching", {}).get("priority", [])

        logger.info(
            f"프로파일 매칭 초기화: {len(self.profile_patterns)} 프로파일 로드"
        )

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
            pattern: 원본 패턴 ("{KBL}DVR{KBR}")

        Returns:
            확장된 패턴 ("(?<![가-힣A-Za-z0-9])DVR(?![가-힣A-Za-z0-9])")
        """
        pattern = pattern.replace("{KBL}", KBL)
        pattern = pattern.replace("{KBR}", KBR)
        return pattern

    def _compile_profile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """프로파일별 키워드 패턴 컴파일"""
        compiled = {}
        keywords = self.config.get("profile_matching", {}).get("keywords", {})

        for profile_name, patterns in keywords.items():
            compiled[profile_name] = []
            for pattern in patterns:
                try:
                    expanded = self._expand_macro(pattern)
                    compiled[profile_name].append(
                        re.compile(expanded, re.IGNORECASE)
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️ 프로파일 '{profile_name}' 패턴 컴파일 실패: {e}"
                    )

        return compiled

    def normalize_text(self, text: str) -> str:
        """
        텍스트 정규화

        Args:
            text: 원본 텍스트

        Returns:
            정규화된 텍스트 (NFKC, 하이픈 통일, 공백 압축)
        """
        # NFKC 정규화
        text = unicodedata.normalize("NFKC", text)

        # 하이픈 통일 (전각/반각 → 표준 하이픈)
        text = re.sub(r"[‐‑‒–—―−]", "-", text)

        # 공백 압축
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def match_profiles(self, query: str) -> List[str]:
        """
        쿼리에서 프로파일 후보 탐지

        Args:
            query: 사용자 쿼리

        Returns:
            매칭된 프로파일 이름 리스트 (우선순위 정렬)
        """
        query_norm = self.normalize_text(query)
        matched = set()

        for profile_name, patterns in self.profile_patterns.items():
            for pattern in patterns:
                if pattern.search(query_norm):
                    matched.add(profile_name)
                    break

        # 우선순위에 따라 정렬
        if matched:
            sorted_profiles = [p for p in self.priority if p in matched]
            # 우선순위 외 프로파일 추가
            sorted_profiles.extend([p for p in matched if p not in self.priority])
        else:
            # 매칭 없으면 우선순위 전체 반환 (fallback)
            sorted_profiles = self.priority.copy()

        logger.info(f"프로파일 매칭: '{query}' → {sorted_profiles}")
        return sorted_profiles

    def get_profile_weights(self) -> Dict[str, float]:
        """프로파일별 가중치 반환"""
        return (
            self.config.get("profile_matching", {})
            .get("multi_profile", {})
            .get("profile_weights", {})
        )

    def get_multi_profile_config(self) -> Dict[str, Any]:
        """다중 프로파일 병합 설정 반환"""
        return self.config.get("profile_matching", {}).get("multi_profile", {})


# 싱글톤 인스턴스
_matcher = None


def get_profile_matcher() -> ProfileMatcher:
    """프로파일 매칭 싱글톤 반환"""
    global _matcher
    if _matcher is None:
        _matcher = ProfileMatcher()
    return _matcher
