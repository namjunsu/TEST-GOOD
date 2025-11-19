"""도메인 동의어 관리 모듈

SEARCH_CONTENT_ONLY 모드에서 브랜드/모델명의 한영/대소문자 변형을 처리합니다.

Usage:
    >>> from app.rag.domain_synonyms import expand_for_strict_content
    >>> expand_for_strict_content("티비로직")
    "티비로직 TVLogic TVLOGIC TV Logic tvlogic"

Architecture:
    - YAML 파일 기반 동의어 사전 (config/domain_synonyms.yaml)
    - 느리게 로딩 (첫 호출 시 한 번만 로드)
    - 캐시된 flat dict 사용 (빠른 조회)
"""

from pathlib import Path
from typing import Dict, List, Set

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

# Singleton pattern: 한 번만 로드
_SYNONYM_DICT: Dict[str, List[str]] = {}
_LOADED = False


def _load_domain_synonyms() -> Dict[str, List[str]]:
    """YAML 파일에서 동의어 사전 로드 (Lazy loading)

    Returns:
        flat dictionary: {"소니": ["소니", "Sony", ...], "sony": ["소니", "Sony", ...]}
    """
    global _SYNONYM_DICT, _LOADED

    if _LOADED:
        return _SYNONYM_DICT

    yaml_path = Path(__file__).parent.parent.parent / "config" / "domain_synonyms.yaml"

    if not yaml_path.exists():
        logger.warning(f"⚠️ 동의어 사전 파일 없음: {yaml_path}, 빈 사전 사용")
        _LOADED = True
        return {}

    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)

        # YAML 구조를 flat dict로 변환
        # {"camera_brands": {"소니": ["소니", "Sony"]}}
        # → {"소니": ["소니", "Sony"], "sony": ["소니", "Sony"]}
        flat_dict = {}

        for category, brands in yaml_data.items():
            if not isinstance(brands, dict):
                continue

            for key, synonyms in brands.items():
                if not isinstance(synonyms, list):
                    continue

                # 원래 키 (예: "소니", "pmw500")
                flat_dict[key] = synonyms

                # 모든 동의어도 같은 리스트를 가리키도록 (양방향 매핑)
                for synonym in synonyms:
                    synonym_lower = synonym.lower()
                    if synonym_lower not in flat_dict:
                        flat_dict[synonym_lower] = synonyms

        _SYNONYM_DICT = flat_dict
        _LOADED = True

        logger.info(f"✅ 동의어 사전 로드 완료: {len(flat_dict)}개 키, {yaml_path}")
        return flat_dict

    except Exception as e:
        logger.error(f"❌ 동의어 사전 로드 실패: {e}")
        _LOADED = True
        return {}


def expand_for_strict_content(query: str) -> str:
    """SEARCH_CONTENT_ONLY 모드용 동의어 확장

    QueryExpander를 쓰지 않고, 브랜드/모델명의 한영/대소문자 변형만 처리합니다.

    Args:
        query: 불용어 제거된 키워드 (예: "티비로직")

    Returns:
        동의어 확장된 쿼리 (예: "티비로직 TVLogic TVLOGIC TV Logic tvlogic")

    Example:
        >>> expand_for_strict_content("티비로직")
        "티비로직 TVLogic TVLOGIC TV Logic tvlogic"

        >>> expand_for_strict_content("eco8000")
        "eco8000 ECO8000 ECO-8000 에코8000"

        >>> expand_for_strict_content("젠하이저")
        "젠하이저 Sennheiser SENNHEISER sennheiser"
    """
    synonym_dict = _load_domain_synonyms()

    tokens = query.lower().split()  # 소문자 변환 후 분리
    expanded_tokens = []
    seen: Set[str] = set()  # 중복 제거용

    for token in tokens:
        # 동의어 사전에서 확장
        if token in synonym_dict:
            variants = synonym_dict[token]
            for v in variants:
                if v not in seen:
                    expanded_tokens.append(v)
                    seen.add(v)
        else:
            # 사전에 없으면 원본 그대로
            if token not in seen:
                expanded_tokens.append(token)
                seen.add(token)

    return " ".join(expanded_tokens)


def get_synonyms(keyword: str) -> List[str]:
    """특정 키워드의 동의어 리스트 반환

    Args:
        keyword: 검색할 키워드 (대소문자 무관)

    Returns:
        동의어 리스트 (없으면 빈 리스트)

    Example:
        >>> get_synonyms("sony")
        ["소니", "Sony", "SONY", "sony"]
    """
    synonym_dict = _load_domain_synonyms()
    return synonym_dict.get(keyword.lower(), [])


def reload_synonyms():
    """동의어 사전 강제 재로드 (테스트/디버깅용)"""
    global _LOADED
    _LOADED = False
    return _load_domain_synonyms()
