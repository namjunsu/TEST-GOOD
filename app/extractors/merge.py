"""필드 병합 및 검증 로직

규칙 기반 추출 결과와 LLM 추출 결과를 병합하여 최종 필드를 구성합니다.
규칙 우선(rule-first) 정책으로 확실한 패턴은 규칙을, 나머지는 LLM 결과를 사용합니다.
"""

from typing import Dict, Any, Optional


def merge_device_fields(rule: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
    """장비 필드 병합 및 검증

    규칙 우선(rule-first) 정책:
    1. 규칙 추출 결과가 유효하면 우선 사용
    2. 규칙 결과가 없으면 LLM 결과 사용
    3. 둘 다 없으면 None

    추가 검증:
    - duration_years: 1~30 범위 체크
    - ip_address: 형식 체크 (정규식으로 이미 검증됨)

    Args:
        rule: 규칙 기반 추출 결과
        llm: LLM 추출 결과

    Returns:
        병합된 필드 dict
    """
    out = {}

    for k in ("model", "manufacturer", "ip_address", "reason", "duration_years"):
        rv = rule.get(k)
        lv = llm.get(k)
        out[k] = rv if _valid(rv) else (lv if _valid(lv) else None)

    # 추가 검증: 연도 숫자 합리성 (1~30년)
    if out["duration_years"] is not None:
        try:
            years = int(out["duration_years"])
            if not (1 <= years <= 30):
                out["duration_years"] = None
            else:
                out["duration_years"] = years
        except (ValueError, TypeError):
            out["duration_years"] = None

    return out


def _valid(v: Optional[Any]) -> bool:
    """필드 값 유효성 체크

    - None: 무효
    - 빈 문자열: 무효
    - 숫자 0: 무효
    - 기타: 유효
    """
    if v is None:
        return False
    if isinstance(v, str):
        return len(v.strip()) > 0
    if isinstance(v, (int, float)):
        return v > 0
    return True
