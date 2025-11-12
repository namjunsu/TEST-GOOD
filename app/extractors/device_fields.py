"""결정적 필드 추출기 (정규식 기반)

DOC_ANCHORED 모드에서 장비 문서의 핵심 필드를 규칙 기반으로 추출합니다.
LLM 추출 결과와 병합하여 정확도를 보장합니다.

개선사항:
- 모델/제조사 패턴 확장 (Hanwha XRN, IDIS, TVLogic, Blackmagic 등)
- 기간 추출 보강 (약/대략/± 변형 흡수)
- IP 우선순위 (RFC1918 사설망 우선)
- 사유 문장 단위 추출 및 스코어링
- 근거(span) 정보 포함 (LLM 병합 및 하이라이트용)
"""

from __future__ import annotations
import re
from typing import Optional, Dict, Any, List, Tuple


# ============================================================================
# 정규식 패턴
# ============================================================================

# IPv4 패턴
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")

# 모델 패턴 (방송 장비 주요 벤더)
MODEL_PATTERNS = [
    r"HRD-?\d{3,4}",                    # Hanwha DVR (예: HRD-442)
    r"XRN-?\d{3,4}[A-Z0-9]*",           # Hanwha NVR (예: XRN-1620B2)
    r"NR-?\d{3,4}[A-Z0-9]*(?:-[A-Z])?", # IDIS NVR (예: NR-3516P-A)
    r"LVM-?\d{3}[A-Z0-9]*",             # TVLogic Monitor (예: LVM-180A)
    r"RMK-?\d{3}[A-Z0-9]*",             # TVLogic Rack (예: RMK-182)
    r"DeckLink\s?[A-Za-z0-9\-\s]+",     # Blackmagic DeckLink (Studio 4K 등)
    r"ATEM\s?[A-Za-z0-9\s\-]+",         # Blackmagic ATEM
    r"Carbonite\s?[A-Z0-9\-]+",         # Ross Carbonite
]
MODEL_RE = re.compile(r"\b(?:" + "|".join(MODEL_PATTERNS) + r")\b", re.IGNORECASE)

# 제조사 정규화 맵 (표기 변형 → 표준 이름)
MANU_MAP = {
    r"\bHanwha(?:\s+Techwin)?\b": "Hanwha Vision",
    r"\bHanwha\s+Vision\b": "Hanwha Vision",
    r"\bIDIS\b": "IDIS",
    r"\bTVLogic\b": "TVLogic",
    r"\bBlackmagic(?:\s+Design)?\b": "Blackmagic Design",
    r"\bRoss\s+Video\b": "Ross Video",
    r"\bRTS\b": "RTS",
    r"\bSony\b": "Sony",
    r"\bCanon\b": "Canon",
    r"\bPanasonic\b": "Panasonic",
}
MANU_RE = re.compile("|".join(MANU_MAP.keys()), re.IGNORECASE)

# 기간 패턴 (약/대략/±, 붙여쓰기/띄어쓰기, 경과/사용/운영/노후/간/째/이상 등)
YEARS_RE = re.compile(
    r"(?:약|대략|\+/-|±)?\s*(\d{1,2})\s*년(?:\s*(?:간|째|이상|초과|경과|사용|운영|노후))?",
    re.IGNORECASE
)

# 교체 사유 키워드
REASON_KEYS = (
    "경과", "노후", "고장", "성능 저하", "단종", "용량 부족",
    "장애", "불안정", "끊김", "스트리밍", "열화", "수명"
)


# ============================================================================
# 헬퍼 함수
# ============================================================================

def _findall_with_spans(pattern: re.Pattern, text: str) -> List[Tuple[str, Tuple[int, int]]]:
    """패턴 매칭 후보와 span 반환

    Args:
        pattern: 정규식 패턴
        text: 검색 대상 텍스트

    Returns:
        List[(매칭 문자열, (start, end))]
    """
    return [(m.group(0), (m.start(), m.end())) for m in pattern.finditer(text)]


def _is_private_ipv4(ip: str) -> bool:
    """RFC1918 사설망 IP 확인

    Args:
        ip: IPv4 주소 문자열

    Returns:
        bool: 사설망 여부 (10.x, 172.16-31.x, 192.168.x)
    """
    if ip.startswith("10.") or ip.startswith("192.168."):
        return True
    # 172.16.0.0 ~ 172.31.255.255
    if ip.startswith("172."):
        try:
            second_octet = int(ip.split(".")[1])
            return 16 <= second_octet <= 31
        except (IndexError, ValueError):
            return False
    return False


def _prefer_private_ipv4(
    candidates: List[Tuple[str, Tuple[int, int]]]
) -> Optional[Tuple[str, Tuple[int, int]]]:
    """사설망 IP 우선 선택

    Args:
        candidates: [(IP, span)] 리스트

    Returns:
        선택된 IP와 span (사설망 우선, 없으면 첫 번째)
    """
    if not candidates:
        return None

    # 사설망 IP 필터링
    private_ips = [c for c in candidates if _is_private_ipv4(c[0])]

    return private_ips[0] if private_ips else candidates[0]


def _split_sentences(text: str) -> List[str]:
    """한국어 문장 분할

    Args:
        text: 전체 텍스트

    Returns:
        List[str]: 문장 리스트
    """
    # 마침표/물음표/느낌표/줄바꿈 기준으로 분할
    # look-behind 대신 단순 split 후 필터링
    sentences = re.split(r"[\.!?\n]+", text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 3]


def _score_reason_sentence(sentence: str) -> float:
    """교체 사유 문장 스코어링

    Args:
        sentence: 후보 문장

    Returns:
        float: 점수 (키워드 밀도 + 길이 적정성)
    """
    # 키워드 히트 수
    keyword_hits = sum(1 for k in REASON_KEYS if k in sentence)

    # 길이 적정성 (8~240자, 최적 길이: 80~160)
    length_score = min(len(sentence), 160) / 160.0

    return keyword_hits * 2.0 + length_score


def _extract_reason(text: str) -> Optional[str]:
    """교체 사유 문장 추출 (문장 단위, 스코어링)

    Args:
        text: 문서 전체 텍스트

    Returns:
        str | None: 교체 사유 문장
    """
    sentences = _split_sentences(text)

    # 키워드 포함 문장 필터링 (너무 짧거나 긴 문장 제외)
    candidates = [
        s for s in sentences
        if any(k in s for k in REASON_KEYS) and 8 <= len(s) <= 240
    ]

    if candidates:
        # 스코어링 후 최고점 문장 선택
        candidates.sort(key=_score_reason_sentence, reverse=True)
        return candidates[0]

    # Fallback: 줄 단위 검색
    for line in text.splitlines():
        line = line.strip()
        if any(k in line for k in REASON_KEYS) and 8 <= len(line) <= 240:
            return line

    return None


def _normalize_manufacturer(raw: Optional[str]) -> Optional[str]:
    """제조사 이름 정규화

    Args:
        raw: 원문 제조사 이름

    Returns:
        str | None: 정규화된 제조사 이름
    """
    if not raw:
        return None

    m = MANU_RE.search(raw)
    if not m:
        return raw

    matched = m.group(0)

    # 매핑 테이블로 정규화
    for pattern, normalized in MANU_MAP.items():
        if re.fullmatch(pattern, matched, re.IGNORECASE):
            return normalized

    return matched


# ============================================================================
# 메인 함수
# ============================================================================

def extract_fields_rule_based(text: str) -> Dict[str, Any]:
    """정규식 기반 필드 추출 (후보 스코어링 포함)

    Args:
        text: 문서 전체 텍스트

    Returns:
        dict: 추출된 필드
            - model: 모델명 (예: "XRN-1620B2")
            - manufacturer: 제조사 (정규화됨, 예: "Hanwha Vision")
            - ip_address: IP 주소 (사설망 우선, 예: "10.120.10.153")
            - reason: 교체 사유 문장
            - duration_years: 사용 기간 (숫자)
            - sources: 근거 정보 (span)
                - model_span: (start, end)
                - manufacturer_span: (start, end)
                - ip_span: (start, end)
                - duration_span: (start, end)

    Example:
        >>> text = "Hanwha Techwin XRN-1620B2 (IP: 10.120.10.153)를 약 7년 사용했으나 HDD 고장으로 교체"
        >>> result = extract_fields_rule_based(text)
        >>> result["model"]
        'XRN-1620B2'
        >>> result["manufacturer"]
        'Hanwha Vision'
        >>> result["duration_years"]
        7
    """
    # 1) 모델 (다수 후보 중 첫 번째)
    model_candidates = _findall_with_spans(MODEL_RE, text)
    model = model_candidates[0][0] if model_candidates else None
    model_span = model_candidates[0][1] if model_candidates else None

    # 2) 제조사 (정규화)
    manu_candidates = _findall_with_spans(MANU_RE, text)
    manu_raw = manu_candidates[0][0] if manu_candidates else None
    manufacturer = _normalize_manufacturer(manu_raw)
    manu_span = manu_candidates[0][1] if manu_candidates else None

    # 3) IP (사설망 우선)
    ip_candidates = _findall_with_spans(IP_RE, text)
    ip_selected = _prefer_private_ipv4(ip_candidates)
    ip_address = ip_selected[0] if ip_selected else None
    ip_span = ip_selected[1] if ip_selected else None

    # 4) 사용 기간 (년)
    duration_years = None
    duration_span = None
    for match in YEARS_RE.finditer(text):
        try:
            duration_years = int(match.group(1))
            duration_span = (match.start(1), match.end(1))
            break
        except (ValueError, IndexError):
            continue

    # 5) 교체 사유 (문장 단위, 스코어링)
    reason = _extract_reason(text)

    return {
        "model": model,
        "manufacturer": manufacturer,
        "ip_address": ip_address,
        "reason": reason,
        "duration_years": duration_years,
        # 근거/span (LLM 병합 및 하이라이트용)
        "sources": {
            "model_span": model_span,
            "manufacturer_span": manu_span,
            "ip_span": ip_span,
            "duration_span": duration_span,
        }
    }


__all__ = ["extract_fields_rule_based"]
