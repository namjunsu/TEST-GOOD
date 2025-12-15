"""도메인 동의어 관리 모듈

브랜드/모델명의 한↔영, 대소문자, 하이픈 변형을 처리합니다.

Architecture:
    1. YAML 기반 동의어 사전: 한글↔영문 매핑 (티비로직 ↔ TVLogic)
    2. 퍼지 매칭: 영문 변형 자동 처리 (TVLogic, TV-Logic, TvLogic)

Usage:
    >>> from app.rag.domain_synonyms import expand_query_smart
    >>> expand_query_smart("티비로직 모니터")
    "티비로직 TVLogic TvLogic TV-Logic TVLOGIC 모니터"
"""

from pathlib import Path

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

# Singleton pattern: 한 번만 로드
_SYNONYM_DICT: dict[str, list[str]] = {}
_LOADED = False


def _load_domain_synonyms() -> dict[str, list[str]]:
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
        with Path(yaml_path).open("r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            logger.warning(f"⚠️ 동의어 사전 파일이 비어있음: {yaml_path}")
            _LOADED = True
            return {}

        # YAML 구조를 flat dict로 변환
        # {"camera_brands": {"소니": ["소니", "Sony"]}}
        # → {"소니": ["소니", "Sony"], "sony": ["소니", "Sony"]}
        flat_dict = {}

        for category, brands in yaml_data.items():
            if not isinstance(brands, dict):
                logger.warning(f"⚠️ 카테고리 '{category}'가 dict가 아님, 건너뜀")
                continue

            for key, synonyms in brands.items():
                if not isinstance(synonyms, list):
                    logger.warning(f"⚠️ 키 '{key}'의 동의어가 list가 아님, 건너뜀")
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

    except yaml.YAMLError as e:
        logger.error(f"❌ YAML 파싱 에러: {e}, 빈 사전으로 계속 진행")
        _LOADED = True
        return {}
    except IOError as e:
        logger.error(f"❌ 파일 읽기 에러: {e}, 빈 사전으로 계속 진행")
        _LOADED = True
        return {}
    except Exception as e:
        logger.error(f"❌ 동의어 사전 로드 실패 (알 수 없는 오류): {e}, 빈 사전으로 계속 진행")
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
    seen: set[str] = set()  # 중복 제거용

    for token in tokens:
        # 동의어 사전에서 확장
        if token in synonym_dict:
            variants = synonym_dict[token]
            for v in variants:
                if v not in seen:
                    expanded_tokens.append(v)
                    seen.add(v)
        # 사전에 없으면 원본 그대로
        elif token not in seen:
            expanded_tokens.append(token)
            seen.add(token)

    return " ".join(expanded_tokens)


def get_synonyms(keyword: str) -> list[str]:
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


def expand_query_smart(query: str, db_path: str = "metadata.db") -> str:
    """스마트 쿼리 확장: YAML 동의어 + 퍼지 매칭 통합

    1단계: YAML 동의어 사전으로 한↔영 변환
    2단계: 퍼지 매칭으로 영문 변형 추가 (하이픈, 대소문자)

    Args:
        query: 원본 쿼리 (예: "티비로직 모니터")
        db_path: DB 경로 (퍼지 매칭용)

    Returns:
        확장된 쿼리 (예: "티비로직 TVLogic TvLogic TV-Logic TVLOGIC 모니터")

    Example:
        >>> expand_query_smart("티비로직")
        "티비로직 TVLogic TvLogic TV-Logic TVLOGIC tvlogic TV Logic"

        >>> expand_query_smart("블랙매직")
        "블랙매직 Blackmagic BlackMagic BLACKMAGIC blackmagic Black Magic"
    """
    # 1단계: YAML 동의어 확장 (한↔영)
    yaml_expanded = expand_for_strict_content(query)

    # 2단계: 퍼지 매칭으로 영문 변형 추가
    try:
        from app.rag.fuzzy_matcher import init_brand_matcher_from_db

        matcher = init_brand_matcher_from_db(db_path)
        fuzzy_expanded = matcher.expand_query(yaml_expanded)

        # 중복 제거하면서 순서 유지
        tokens = fuzzy_expanded.split()
        seen: set[str] = set()
        unique_tokens = []
        for t in tokens:
            t_lower = t.lower()
            if t_lower not in seen:
                unique_tokens.append(t)
                seen.add(t_lower)

        return " ".join(unique_tokens)

    except ImportError:
        logger.warning("⚠️ fuzzy_matcher 모듈 없음, YAML 동의어만 사용")
        return yaml_expanded
    except Exception as e:
        logger.warning(f"⚠️ 퍼지 매칭 실패: {e}, YAML 동의어만 사용")
        return yaml_expanded
