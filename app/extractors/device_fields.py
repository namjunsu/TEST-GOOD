"""결정적 필드 추출기 (정규식 기반)

DOC_ANCHORED 모드에서 장비 문서의 핵심 필드를 규칙 기반으로 추출합니다.
LLM 추출 결과와 병합하여 정확도를 보장합니다.
"""

import re
from typing import Optional, Dict, Any

# 정규식 패턴
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
MODEL_RE = re.compile(r"\bHRD-?\d{3,4}\b", re.IGNORECASE)
MANU_RE = re.compile(r"\bHanwha(?:\s+Techwin)?\b", re.IGNORECASE)
YEARS_RE = re.compile(r"약\s*(\d+)\s*년|(\d+)\s*년\s*(?:경과|사용|노후|운영|간)")

# 교체 사유 키워드
REASON_KEYS = ("경과", "노후", "고장", "성능 저하", "단종", "용량 부족", "장애", "불안정", "끊김", "스트리밍")


def extract_fields_rule_based(text: str) -> Dict[str, Any]:
    """정규식 기반 필드 추출

    Args:
        text: 문서 전체 텍스트

    Returns:
        추출된 필드 dict:
        - model: 모델명 (예: "HRD-442")
        - manufacturer: 제조사 (예: "Hanwha Techwin")
        - ip_address: IP 주소 (예: "10.120.10.153")
        - reason: 교체 사유 (문장 인용)
        - duration_years: 사용 기간 (숫자)
    """
    model = _search(MODEL_RE, text)
    manu = _search(MANU_RE, text)
    ip = _search(IP_RE, text)
    reason = _extract_reason(text)

    # duration_years: 숫자만 반환 (약 N년 우선, 없으면 N년 경과)
    dy = None
    m = YEARS_RE.search(text)
    if m:
        dy = int(m.group(1) if m.group(1) else m.group(2))

    return {
        "model": model,
        "manufacturer": manu,
        "ip_address": ip,
        "reason": reason,
        "duration_years": dy,
    }


def _search(pattern: re.Pattern, text: str) -> Optional[str]:
    """정규식 패턴 검색 (첫 매치 반환)"""
    m = pattern.search(text)
    return m.group(0) if m else None


def _extract_reason(text: str) -> Optional[str]:
    """교체 사유 문장 추출

    REASON_KEYS를 포함하는 문장을 우선 추출합니다.
    """
    for line in re.split(r"[\n\r]+", text):
        line = line.strip()
        if any(k in line for k in REASON_KEYS) and 10 <= len(line) <= 200:
            return line
    return None
