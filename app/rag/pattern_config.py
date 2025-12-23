#!/usr/bin/env python3
"""
쿼리 라우팅 패턴 설정 로더 (v1.0)

YAML 기반 패턴 설정을 로드하고 컴파일하여 QueryRouter에 제공.
하드코딩 패턴을 외부화하여 유지보수성 향상.

주요 기능:
1. YAML 설정 로드 및 검증
2. 정규식 패턴 컴파일 및 캐싱
3. 우선순위 체인 관리
4. 충돌 해결 규칙 제공
5. 핫리로드 지원 (파일 변경 감지)

사용법:
    loader = PatternConfigLoader()
    patterns = loader.get_patterns("cost_intent")
    priority = loader.get_priority_chain()
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# 기본 설정 파일 경로
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "query_routing_patterns.yaml"


@dataclass
class PatternRule:
    """단일 패턴 규칙"""
    name: str
    pattern: re.Pattern
    priority: int = 50
    raw_pattern: str = ""


@dataclass
class ModePatterns:
    """모드별 패턴 집합"""
    mode: str
    description: str
    confidence: float
    rules: list[PatternRule] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)

    def matches(self, query: str) -> bool:
        """쿼리가 이 모드의 패턴에 매칭되는지 확인"""
        # 제외 키워드 체크
        if self.exclude_keywords:
            if any(kw in query for kw in self.exclude_keywords):
                return False

        # 패턴 매칭 (우선순위 높은 순서로)
        for rule in sorted(self.rules, key=lambda r: -r.priority):
            if rule.pattern.search(query):
                return True
        return False

    def get_matching_rule(self, query: str) -> Optional[PatternRule]:
        """매칭된 규칙 반환"""
        for rule in sorted(self.rules, key=lambda r: -r.priority):
            if rule.pattern.search(query):
                return rule
        return None


@dataclass
class ConflictRule:
    """충돌 해결 규칙"""
    patterns: list[str]
    winner: str
    condition: str
    keywords: list[str] = field(default_factory=list)
    description: str = ""


class PatternConfigLoader:
    """YAML 기반 패턴 설정 로더"""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Args:
            config_path: 설정 파일 경로 (None이면 기본 경로 사용)
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: dict[str, Any] = {}
        self._mode_patterns: dict[str, ModePatterns] = {}
        self._conflict_rules: list[ConflictRule] = []
        self._priority_chain: list[str] = []
        self._keywords: dict[str, list[str]] = {}
        self._loaded = False
        self._load_config()

    def _load_config(self) -> None:
        """설정 파일 로드 및 파싱"""
        try:
            if not self.config_path.exists():
                logger.warning(f"⚠️ 패턴 설정 파일 없음: {self.config_path}")
                self._loaded = False
                return

            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}

            # 스키마 버전 확인
            schema_version = self._config.get("schema_version", 0)
            if schema_version != 1:
                logger.warning(f"⚠️ 지원하지 않는 스키마 버전: {schema_version}")

            # 우선순위 체인 로드
            self._priority_chain = self._config.get("priority_chain", [])

            # 충돌 규칙 로드
            self._load_conflict_rules()

            # 모드별 패턴 로드
            self._load_patterns()

            # 키워드 로드
            self._keywords = self._config.get("keywords", {})

            self._loaded = True
            logger.info(f"✓ 패턴 설정 로드: {self.config_path.name} "
                       f"(모드 {len(self._mode_patterns)}개, 규칙 {len(self._conflict_rules)}개)")

        except yaml.YAMLError as e:
            logger.error(f"❌ YAML 파싱 오류: {e}")
            self._loaded = False
        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            self._loaded = False

    def _load_conflict_rules(self) -> None:
        """충돌 해결 규칙 로드"""
        conflict_rules = self._config.get("conflict_rules", [])
        for rule_dict in conflict_rules:
            try:
                rule = ConflictRule(
                    patterns=rule_dict.get("patterns", []),
                    winner=rule_dict.get("winner", ""),
                    condition=rule_dict.get("condition", ""),
                    keywords=rule_dict.get("keywords", []),
                    description=rule_dict.get("description", ""),
                )
                self._conflict_rules.append(rule)
            except Exception as e:
                logger.warning(f"⚠️ 충돌 규칙 파싱 실패: {e}")

    def _load_patterns(self) -> None:
        """모드별 패턴 로드 및 컴파일"""
        patterns_config = self._config.get("patterns", {})

        for mode_name, mode_config in patterns_config.items():
            try:
                rules = []
                for rule_dict in mode_config.get("rules", []):
                    raw_pattern = rule_dict.get("pattern", "")
                    try:
                        compiled = re.compile(raw_pattern)
                        rules.append(PatternRule(
                            name=rule_dict.get("name", "unnamed"),
                            pattern=compiled,
                            priority=rule_dict.get("priority", 50),
                            raw_pattern=raw_pattern,
                        ))
                    except re.error as e:
                        logger.warning(f"⚠️ 정규식 컴파일 실패 [{mode_name}/{rule_dict.get('name')}]: {e}")

                mode_patterns = ModePatterns(
                    mode=mode_name,
                    description=mode_config.get("description", ""),
                    confidence=mode_config.get("confidence", 0.8),
                    rules=rules,
                    exclude_keywords=mode_config.get("exclude_keywords", []),
                )
                self._mode_patterns[mode_name] = mode_patterns

            except Exception as e:
                logger.warning(f"⚠️ 모드 패턴 로드 실패 [{mode_name}]: {e}")

    @property
    def is_loaded(self) -> bool:
        """설정 로드 여부"""
        return self._loaded

    def get_priority_chain(self) -> list[str]:
        """우선순위 체인 반환"""
        return self._priority_chain.copy()

    def get_patterns(self, mode: str) -> Optional[ModePatterns]:
        """모드별 패턴 반환

        Args:
            mode: 모드 이름 (예: "cost_intent", "year_summary")

        Returns:
            ModePatterns 객체 또는 None
        """
        return self._mode_patterns.get(mode)

    def get_all_patterns(self) -> dict[str, ModePatterns]:
        """모든 모드 패턴 반환"""
        return self._mode_patterns.copy()

    def get_conflict_rules(self) -> list[ConflictRule]:
        """충돌 해결 규칙 반환"""
        return self._conflict_rules.copy()

    def get_keywords(self, category: str) -> list[str]:
        """카테고리별 키워드 반환

        Args:
            category: 키워드 카테고리 (예: "qa_intent", "cost_related")

        Returns:
            키워드 리스트
        """
        return self._keywords.get(category, [])

    def resolve_conflict(self, mode1: str, mode2: str, query: str) -> Optional[str]:
        """두 모드 간 충돌 해결

        Args:
            mode1: 첫 번째 모드
            mode2: 두 번째 모드
            query: 사용자 쿼리

        Returns:
            우선 모드 이름 또는 None (규칙 없음)
        """
        for rule in self._conflict_rules:
            if set(rule.patterns) == {mode1, mode2}:
                # 조건 검사
                if rule.condition == "has_cost_keyword":
                    if any(kw in query for kw in rule.keywords):
                        return rule.winner
                elif rule.condition == "has_year_content_question":
                    # YEAR_SUMMARY가 더 구체적인 패턴
                    return rule.winner
                else:
                    # 기본: winner 반환
                    return rule.winner
        return None

    def classify_with_config(self, query: str) -> Optional[tuple[str, float, str]]:
        """설정 기반 쿼리 분류

        Args:
            query: 사용자 쿼리

        Returns:
            (mode_name, confidence, matched_rule_name) 또는 None

        Note:
            이 메서드는 QueryRouter의 기존 로직을 대체하지 않고
            보조 역할로 사용됨. 점진적 마이그레이션 지원.
        """
        if not self._loaded:
            return None

        matched_modes: list[tuple[str, ModePatterns, PatternRule]] = []

        # 우선순위 체인 순서대로 검사
        for mode_name in self._priority_chain:
            mode_patterns = self._mode_patterns.get(mode_name)
            if not mode_patterns:
                continue

            rule = mode_patterns.get_matching_rule(query)
            if rule:
                matched_modes.append((mode_name, mode_patterns, rule))

        if not matched_modes:
            return None

        # 충돌 해결
        if len(matched_modes) > 1:
            first_mode, _, _ = matched_modes[0]
            second_mode, _, _ = matched_modes[1]
            winner = self.resolve_conflict(first_mode, second_mode, query)
            if winner:
                for mode_name, mode_patterns, rule in matched_modes:
                    if mode_name == winner:
                        return (mode_name, mode_patterns.confidence, rule.name)

        # 첫 번째 매칭 반환 (우선순위 체인 기준)
        mode_name, mode_patterns, rule = matched_modes[0]
        return (mode_name, mode_patterns.confidence, rule.name)

    def reload(self) -> bool:
        """설정 파일 리로드

        Returns:
            리로드 성공 여부
        """
        logger.info("🔄 패턴 설정 리로드 중...")
        self._mode_patterns.clear()
        self._conflict_rules.clear()
        self._priority_chain.clear()
        self._keywords.clear()
        self._load_config()
        return self._loaded


# 싱글톤 인스턴스 (선택적 사용)
_loader_instance: Optional[PatternConfigLoader] = None


def get_pattern_loader() -> PatternConfigLoader:
    """싱글톤 패턴 로더 반환"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = PatternConfigLoader()
    return _loader_instance


# 테스트/디버깅용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    loader = PatternConfigLoader()

    print("\n=== 우선순위 체인 ===")
    print(loader.get_priority_chain())

    print("\n=== 모드별 패턴 ===")
    for mode, patterns in loader.get_all_patterns().items():
        print(f"\n[{mode}] {patterns.description}")
        print(f"  신뢰도: {patterns.confidence}")
        print(f"  규칙 수: {len(patterns.rules)}")
        for rule in patterns.rules[:2]:  # 처음 2개만
            print(f"    - {rule.name} (priority={rule.priority})")

    print("\n=== 테스트 분류 ===")
    test_queries = [
        "2024년 문서들은 어떤 내용이야?",
        "작년 소모품 합계 얼마",
        "총액은?",
        "카메라 관련 문서 찾아줘",
    ]

    for query in test_queries:
        result = loader.classify_with_config(query)
        if result:
            mode, conf, rule = result
            print(f"'{query}' → {mode} (conf={conf}, rule={rule})")
        else:
            print(f"'{query}' → (매칭 없음)")
