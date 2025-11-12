"""필드 병합 및 검증 로직 (rule-first + provenance + normalization)

규칙 기반 추출 결과와 LLM 추출 결과를 병합하여 최종 필드를 구성합니다.
규칙 우선(rule-first) 정책으로 확실한 패턴은 규칙을, 나머지는 LLM 결과를 사용합니다.

개선사항 (2025-11-11):
- 근거(provenance) 추적: 어떤 소스에서 선택되었는지 기록
- 제조사/모델 정규화: 일관된 표기로 변환
- IP 우선순위 정책: 사설망(RFC1918) 우선
- reason 문장 품질 필터: 길이 검증 (8~240자)
- duration_years 캐스팅 강화: 문자열 숫자도 안전하게 처리
- 모델-제조사 상관 검증: 불일치 경고
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# IP 주소 처리 (RFC1918 사설망 우선)
# ============================================================================

PRIVATE_PREFIXES = ("10.", "192.168.", "172.")


def _is_private_ip(ip: str) -> bool:
    """RFC1918 사설망 IP 확인

    Args:
        ip: IPv4 주소 문자열

    Returns:
        bool: 사설망 여부 (10.x, 172.16-31.x, 192.168.x)
    """
    if not isinstance(ip, str):
        return False

    # 10.x.x.x 또는 192.168.x.x
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


def _pick_ip(rule_ip: Optional[str], llm_ip: Optional[str]) -> Tuple[Optional[str], str]:
    """사설망 우선 + rule 우선 정책으로 IP 선택

    Args:
        rule_ip: 규칙 추출 IP
        llm_ip: LLM 추출 IP

    Returns:
        (선택된 IP, 소스 "rule"|"llm"|"none")

    Policy:
        1. 둘 다 사설망 → rule 우선
        2. 하나만 사설망 → 사설망 선택
        3. 둘 다 공인 → rule 우선
        4. 둘 다 없음 → None
    """
    candidates = [
        (ip, src) for ip, src in [(rule_ip, "rule"), (llm_ip, "llm")]
        if isinstance(ip, str) and ip.strip()
    ]

    if not candidates:
        return None, "none"

    # 사설망 IP 필터링
    private_ips = [(ip, src) for ip, src in candidates if _is_private_ip(ip)]

    if private_ips:
        # rule이 사설망이면 rule, 아니면 첫 번째 사설망
        for ip, src in private_ips:
            if src == "rule":
                return ip, "rule"
        return private_ips[0]

    # 둘 다 공인 IP → rule 우선
    return rule_ip or llm_ip, "rule" if rule_ip else "llm"


# ============================================================================
# 필드별 정규화 함수
# ============================================================================

# 제조사 정규화 맵 (표기 변형 → 표준 이름)
_MANU_NORMALIZE = {
    "hanwha techwin": "Hanwha Vision",
    "hanwha vision": "Hanwha Vision",
    "hanwha": "Hanwha Vision",
    "idis": "IDIS",
    "tvlogic": "TVLogic",
    "blackmagic": "Blackmagic Design",
    "blackmagic design": "Blackmagic Design",
    "ross video": "Ross Video",
    "ross": "Ross Video",
    "rts": "RTS",
    "sony": "Sony",
    "canon": "Canon",
    "panasonic": "Panasonic",
}


def _normalize_manufacturer(v: Optional[str]) -> Optional[str]:
    """제조사 이름 정규화

    Args:
        v: 원본 제조사 이름

    Returns:
        정규화된 제조사 이름 또는 None

    Example:
        >>> _normalize_manufacturer("Hanwha Techwin")
        'Hanwha Vision'
        >>> _normalize_manufacturer("blackmagic")
        'Blackmagic Design'
    """
    if not v or not isinstance(v, str):
        return v

    # 소문자로 변환 후 맵 조회
    key = v.strip().lower()
    normalized = _MANU_NORMALIZE.get(key)

    if normalized:
        logger.debug(f"제조사 정규화: '{v}' → '{normalized}'")
        return normalized

    # 맵에 없으면 원본 trim 반환
    return v.strip()


def _normalize_model(v: Optional[str]) -> Optional[str]:
    """모델명 정규화 (대소문자, 하이픈 일관화)

    Args:
        v: 원본 모델명

    Returns:
        정규화된 모델명 또는 None

    Example:
        >>> _normalize_model("hrd442")
        'HRD-442'
        >>> _normalize_model("XRN1620B2")
        'XRN-1620B2'
        >>> _normalize_model("NR3516PA")
        'NR-3516PA'
    """
    if not v or not isinstance(v, str):
        return v

    # 대문자로 변환
    s = v.strip().upper()

    # 하이픈이 없으면 영문자 블록과 숫자 블록 사이에 하이픈 삽입
    if "-" not in s:
        # 패턴: 문자열 시작 부분의 영문자+ 뒤에 오는 첫 숫자 앞에만 하이픈 삽입
        # (중간의 "B2" 같은 패턴은 그대로 유지)
        s = re.sub(r"^([A-Z]+)(\d)", r"\1-\2", s)

    # 이중 하이픈 축소
    s = s.replace("--", "-")

    if s != v.strip():
        logger.debug(f"모델명 정규화: '{v}' → '{s}'")

    return s


def _normalize_reason(v: Optional[str]) -> Optional[str]:
    """교체 사유 문장 품질 필터

    Args:
        v: 원본 사유 문장

    Returns:
        검증 통과 시 원본, 실패 시 None

    Rules:
        - 길이: 8~240자
        - 너무 짧거나 긴 문장 제거
    """
    if not v or not isinstance(v, str):
        return v

    s = v.strip()

    # 길이 필터 (8~240자)
    if not (8 <= len(s) <= 240):
        logger.debug(f"사유 문장 길이 필터: len={len(s)}, 허용 범위=8~240")
        return None

    return s


def _cast_years(v: Any) -> Optional[int]:
    """사용 기간을 정수로 안전하게 캐스팅

    Args:
        v: 원본 값 (int, str, float 등)

    Returns:
        1~30 범위의 정수 또는 None

    Example:
        >>> _cast_years("7")
        7
        >>> _cast_years("약 10")
        None  # 문자 포함
        >>> _cast_years(25)
        25
        >>> _cast_years(35)
        None  # 범위 초과
    """
    if v is None:
        return None

    try:
        # 문자열은 strip 후 int 변환
        i = int(str(v).strip())

        # 범위 검증 (1~30년)
        if not (1 <= i <= 30):
            logger.debug(f"사용 기간 범위 초과: {i}년, 허용=1~30")
            return None

        return i

    except (ValueError, TypeError):
        logger.debug(f"사용 기간 캐스팅 실패: {v!r}")
        return None


# ============================================================================
# 유효성 검증
# ============================================================================

def _valid(v: Optional[Any]) -> bool:
    """필드 값 유효성 체크

    Args:
        v: 검증 대상 값

    Returns:
        bool: 유효 여부

    Rules:
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


# ============================================================================
# 모델-제조사 상관 검증
# ============================================================================

def _validate_model_manufacturer(
    model: Optional[str], manufacturer: Optional[str]
) -> List[str]:
    """모델명과 제조사 간 상관 검증

    Args:
        model: 모델명
        manufacturer: 제조사

    Returns:
        경고 메시지 리스트 (상관 불일치 시)

    Example:
        >>> _validate_model_manufacturer("HRD-442", "IDIS")
        ['모델-제조사 불일치: HRD/XRN 계열은 Hanwha Vision 제품입니다']
    """
    warnings: List[str] = []

    if not model or not manufacturer:
        return warnings

    # Hanwha Vision 제품 패턴: HRD, XRN
    if model.startswith(("HRD", "XRN")):
        if manufacturer != "Hanwha Vision":
            warnings.append(
                f"모델-제조사 불일치: {model}은 Hanwha Vision 제품인데 "
                f"제조사가 '{manufacturer}'로 기록됨"
            )

    # IDIS 제품 패턴: NR-xxxx
    if re.match(r"^NR-\d", model or ""):
        if manufacturer != "IDIS":
            warnings.append(
                f"모델-제조사 불일치: {model}은 IDIS 제품인데 "
                f"제조사가 '{manufacturer}'로 기록됨"
            )

    # TVLogic 제품 패턴: LVM, RMK
    if model.startswith(("LVM", "RMK")):
        if manufacturer != "TVLogic":
            warnings.append(
                f"모델-제조사 불일치: {model}은 TVLogic 제품인데 "
                f"제조사가 '{manufacturer}'로 기록됨"
            )

    # Blackmagic 제품 패턴: DeckLink, ATEM
    if "DECKLINK" in model or "ATEM" in model:
        if manufacturer != "Blackmagic Design":
            warnings.append(
                f"모델-제조사 불일치: {model}은 Blackmagic Design 제품인데 "
                f"제조사가 '{manufacturer}'로 기록됨"
            )

    return warnings


# ============================================================================
# 메인 병합 함수
# ============================================================================

def merge_device_fields(rule: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
    """장비 필드 병합 및 검증 (개선판: provenance + normalization + validation)

    규칙 우선(rule-first) 정책:
    1. 규칙 추출 결과가 유효하면 우선 사용
    2. 규칙 결과가 없으면 LLM 결과 사용
    3. 둘 다 없으면 None
    4. IP는 사설망 우선 정책 적용
    5. 모든 필드 정규화 후 반환

    Args:
        rule: 규칙 기반 추출 결과
            {model, manufacturer, ip_address, reason, duration_years, sources}
        llm: LLM 추출 결과
            {model, manufacturer, ip_address, reason, duration_years}

    Returns:
        병합된 필드 dict:
        {
            "model": str | None,
            "manufacturer": str | None,
            "ip_address": str | None,
            "reason": str | None,
            "duration_years": int | None,
            "_meta": {
                "chosen": Dict[str, str],      # 필드별 소스 ("rule"|"llm"|"none")
                "rejected": Dict[str, Dict],   # 충돌 시 버려진 값
                "warnings": List[str]          # 검증 경고
            }
        }

    Example:
        >>> rule = {"model": "HRD442", "manufacturer": "Hanwha Techwin", ...}
        >>> llm = {"model": "HRD-442", "manufacturer": "Hanwha Vision", ...}
        >>> result = merge_device_fields(rule, llm)
        >>> result["model"]
        'HRD-442'
        >>> result["manufacturer"]
        'Hanwha Vision'
        >>> result["_meta"]["chosen"]["model"]
        'rule'
    """
    out: Dict[str, Any] = {}
    chosen: Dict[str, str] = {}
    rejected: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = []

    # 1) model 병합 + 정규화
    r_model, l_model = rule.get("model"), llm.get("model")
    model = r_model if _valid(r_model) else (l_model if _valid(l_model) else None)
    out["model"] = _normalize_model(model)
    chosen["model"] = "rule" if _valid(r_model) else ("llm" if _valid(l_model) else "none")

    if r_model != l_model and _valid(r_model) and _valid(l_model):
        rejected["model"] = {"rule": r_model, "llm": l_model}
        logger.debug(f"model 충돌: rule={r_model!r}, llm={l_model!r} → 선택={chosen['model']}")

    # 2) manufacturer 병합 + 정규화
    r_manu, l_manu = rule.get("manufacturer"), llm.get("manufacturer")
    manu = r_manu if _valid(r_manu) else (l_manu if _valid(l_manu) else None)
    out["manufacturer"] = _normalize_manufacturer(manu)
    chosen["manufacturer"] = "rule" if _valid(r_manu) else ("llm" if _valid(l_manu) else "none")

    if r_manu != l_manu and _valid(r_manu) and _valid(l_manu):
        rejected["manufacturer"] = {"rule": r_manu, "llm": l_manu}
        logger.debug(f"manufacturer 충돌: rule={r_manu!r}, llm={l_manu!r} → 선택={chosen['manufacturer']}")

    # 3) ip_address 병합 (사설망 우선 정책)
    r_ip, l_ip = rule.get("ip_address"), llm.get("ip_address")
    ip, ip_source = _pick_ip(r_ip, l_ip)
    out["ip_address"] = ip
    chosen["ip_address"] = ip_source

    if r_ip != l_ip and _valid(r_ip) and _valid(l_ip):
        rejected["ip_address"] = {"rule": r_ip, "llm": l_ip}

        # 사설망 우선 경고
        if r_ip and l_ip:
            r_private = _is_private_ip(r_ip)
            l_private = _is_private_ip(l_ip)

            if l_private and not r_private:
                warnings.append(
                    f"IP 우선순위: rule={r_ip} (공인), llm={l_ip} (사설망) → "
                    f"사설망 우선으로 '{l_ip}' 선택"
                )
            elif r_private and not l_private:
                warnings.append(
                    f"IP 우선순위: rule={r_ip} (사설망), llm={l_ip} (공인) → "
                    f"사설망 우선으로 '{r_ip}' 선택"
                )

    # 4) reason 병합 + 길이 필터
    r_reason, l_reason = rule.get("reason"), llm.get("reason")
    reason = _normalize_reason(r_reason) or _normalize_reason(l_reason)
    out["reason"] = reason
    chosen["reason"] = (
        "rule" if _normalize_reason(r_reason)
        else ("llm" if _normalize_reason(l_reason) else "none")
    )

    if r_reason != l_reason and _valid(r_reason) and _valid(l_reason):
        rejected["reason"] = {"rule": r_reason, "llm": l_reason}

    # 5) duration_years 병합 + 캐스팅
    r_years, l_years = rule.get("duration_years"), llm.get("duration_years")
    years = _cast_years(r_years)
    if years is None:
        years = _cast_years(l_years)
    out["duration_years"] = years
    chosen["duration_years"] = (
        "rule" if _cast_years(r_years) is not None
        else ("llm" if _cast_years(l_years) is not None else "none")
    )

    if r_years != l_years and (_cast_years(r_years) or _cast_years(l_years)):
        rejected["duration_years"] = {"rule": r_years, "llm": l_years}

    # 6) 모델-제조사 상관 검증
    correlation_warnings = _validate_model_manufacturer(
        out["model"], out["manufacturer"]
    )
    warnings.extend(correlation_warnings)

    # 7) 메타 정보 첨부
    out["_meta"] = {
        "chosen": chosen,
        "rejected": rejected,
        "warnings": warnings,
    }

    # 로깅
    if warnings:
        logger.warning(f"장비 필드 병합 경고 ({len(warnings)}개): {warnings}")

    extracted = [k for k in out.keys() if k != "_meta" and out[k] is not None]
    logger.info(
        f"장비 필드 병합 완료: {len(extracted)}개 필드 추출 "
        f"({', '.join(extracted)})"
    )

    return out


__all__ = ["merge_device_fields"]
