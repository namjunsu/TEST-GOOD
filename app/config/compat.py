"""
Configuration Compatibility Layer (Schema v0 → v1)
==========================================

하위 호환을 위해 구형 설정 파일을 v1 스키마로 정규화합니다.

변환 규칙:
1. OCR 모드 통합: ocr_enabled/ocr_fallback → ocr_mode
2. Doctype 기본값: weight=1.0, negative_keywords=[]
3. Author stoplist 정규화: list → dict
"""

from typing import Any, Dict


def normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    구형 설정(schema v0)을 v1 스키마로 정규화합니다.

    Args:
        cfg: 원본 설정 딕셔너리

    Returns:
        정규화된 설정 딕셔너리 (v1 호환)

    Example:
        >>> cfg = {"ingestion": {"ocr_enabled": False, "ocr_fallback": True}}
        >>> normalized = normalize_config(cfg)
        >>> normalized["ingestion"]["ocr_mode"]
        'fallback'
    """
    # schema_version이 없으면 v0으로 간주
    if "schema_version" not in cfg:
        cfg["schema_version"] = 0

    # ===== 1. OCR 모드 통합 =====
    ing = cfg.setdefault("ingestion", {})
    if "ocr_mode" not in ing:
        # 구형 필드 읽기
        enabled = bool(ing.get("ocr_enabled", False))
        fallback = bool(ing.get("ocr_fallback", False))

        # 변환 로직
        if not enabled and not fallback:
            ing["ocr_mode"] = "off"
        elif not enabled and fallback:
            ing["ocr_mode"] = "fallback"
        else:
            ing["ocr_mode"] = "force"

        # 구형 필드 제거 (선택적)
        ing.pop("ocr_enabled", None)
        ing.pop("ocr_fallback", None)

    # ===== 2. Doctype 기본값 보정 =====
    for name, rule in cfg.get("doctype", {}).items():
        if isinstance(rule, dict):
            rule.setdefault("weight", 1.0)
            rule.setdefault("negative_keywords", [])

    # ===== 3. Author stoplist 정규화 =====
    meta = cfg.setdefault("metadata", {})
    ast = meta.get("author_stoplist")

    # list 형태면 dict로 변환
    if isinstance(ast, list):
        meta["author_stoplist"] = {
            "normalize": True,
            "match": "exact_token",
            "values": ast,
        }

    # 스키마 버전 갱신
    if cfg["schema_version"] == 0:
        cfg["schema_version"] = 1

    return cfg


def is_legacy_config(cfg: Dict[str, Any]) -> bool:
    """
    구형 설정 파일인지 확인합니다.

    Args:
        cfg: 설정 딕셔너리

    Returns:
        True if schema v0, False if v1+
    """
    return cfg.get("schema_version", 0) < 1


def validate_ocr_mode(mode: str) -> bool:
    """
    OCR 모드 값이 유효한지 검증합니다.

    Args:
        mode: OCR 모드 문자열

    Returns:
        True if valid, False otherwise
    """
    return mode in ("off", "fallback", "force")
