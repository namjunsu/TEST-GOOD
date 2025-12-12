"""금액·표 추출 모듈 (deterministic extractor)

정규표현식 기반 금액 필드 추출기
LLM은 구조 재구성 및 인용만 담당, 계산은 하지 않음

개선사항 (2025-11-11):
- 통화 단위 정규화 (억/만원/원 혼용 처리)
- 곱셈/범위 표기 대응 (3 × 5, 3 EA x 550,000원)
- VAT 포함/별도/면세 플래그 및 검증 분기
- 수량·단가 표기 다양성 (SET/세트/대/본/EA, 영문 헤더)
- 원문/정규화문 2트랙 탐색 (OCR 노이즈 대응)
- 근거(span) 반환 (프론트 하이라이트/추적용)
"""

import re
from typing import Any, Optional

from app.core.logging import get_logger
from config.constants import FinanceExtractorConfig

logger = get_logger(__name__)


# ============================================================================
# 공통 패턴 및 유틸리티
# ============================================================================

# 숫자 패턴 (앞자리는 숫자로 시작, 쉼표/점 혼용 OCR 대응)
NUM = r"(\d+(?:[,\.]\d+)*)"

# 원화 단위
WON_UNIT = r"(원|만원|억|억원|KRW|₩)?"

# 느슨한 공백
SEP = r"[\s]*"

# 수량 단위/헤더 확장
QTY_UNIT = r"(?:EA|ea|SET|set|세트|대|본|개|장|U|u)?"
QTY_HEADERS = r"(?:수량|Qty|QTY|수\s*량)"

# 금액 헤더 확장
AMOUNT_HEADERS = r"(?:금액|공급가액|공급|소계|AMOUNT|Amount)"
UNIT_PRICE_HEADERS = r"(?:단가|Unit\s*Price|UNIT\s*PRICE|개당)"
TOTAL_HEADERS = r"(?:총액|합계|총\s?계|계|TOTAL|Total)"
VAT_HEADERS = r"(?:부가(?:가치)?세|VAT|세액|Tax)"

# 곱셈 표기 (×, x, *, 곱)
MUL = r"(?:x|×|\*|곱)"


# ============================================================================
# 통화 단위 정규화
# ============================================================================

def normalize_currency(num: str, unit: Optional[str]) -> Optional[int]:
    """통화 단위를 원 단위로 정규화

    Args:
        num: 숫자 문자열 (예: "1,200", "1.2", "2,300")
        unit: 단위 ("원", "만원", "억", "억원", "KRW", "₩", None)

    Returns:
        원 단위 정수 또는 None

    Example:
        >>> normalize_currency("1,200", "만원")
        12000000
        >>> normalize_currency("1.5", "억원")
        150000000
    """
    try:
        # 쉼표 제거 및 소수점 처리 (OCR에서 소수점이 들어올 수 있음)
        n = float(num.replace(",", ""))
    except (ValueError, AttributeError):
        return None

    # 단위별 스케일 적용
    scale = 1
    if unit in ("만원",):
        scale = 10_000
    elif unit in ("억", "억원"):
        scale = 100_000_000
    # KRW/₩/원/None은 scale=1

    return int(round(n * scale))


def normalize_mixed_currency(text: str) -> Optional[int]:
    """혼합 통화 표기 처리 (예: "1억 2,300만원")

    Args:
        text: 검색 대상 텍스트

    Returns:
        원 단위 정수 또는 None

    Example:
        >>> normalize_mixed_currency("1억 2,300만원")
        123000000
        >>> normalize_mixed_currency("5억원")
        500000000
    """
    # 패턴: "1억" 또는 "1억 2,300만원" 형태
    pat = re.compile(
        rf"(?P<e>{NUM})\s*(?P<eu>억|억원)(?:\s*(?P<m>{NUM})\s*(?P<mu>만원))?",
        re.IGNORECASE,
    )

    m = pat.search(text)
    if not m:
        return None

    total = 0

    # 억 단위 처리
    if m.group("e"):
        e_val = normalize_currency(m.group("e"), m.group("eu"))
        if e_val:
            total += e_val

    # 만 단위 처리
    if m.group("m"):
        m_val = normalize_currency(m.group("m"), "만원")
        if m_val:
            total += m_val

    return total if total > 0 else None


# ============================================================================
# OCR 전처리 (원문/정규화문 2트랙)
# ============================================================================

def _preprocess_dual(text: str) -> tuple[str, str]:
    """OCR 텍스트를 원문/정규화문 2트랙으로 전처리

    Args:
        text: 원본 OCR 텍스트

    Returns:
        (원본, 정규화본) 튜플

    Notes:
        - 원본: 그대로 유지 (일부 패턴은 원문에서만 매칭됨)
        - 정규화본: 공백 압축, 단위 분리, 구분자 정리
    """
    raw = text

    # 정규화본: 공백만 압축 (탭 → 공백, 연속 공백 → 단일 공백)
    norm = re.sub(r"[ \t]+", " ", text)

    # 숫자와 단위가 붙은 케이스 분리 (예: "1,200원" → "1,200 원")
    # 주의: 단위가 실제로 있을 때만 공백 삽입 (optional 제거)
    norm = re.sub(r"(\d)(원|만원|억|억원|KRW|₩)", r"\1 \2", norm)

    # 헤더/구분자 주변 공백 정리 (예: "단가:1,200원" → "단가: 1,200원")
    norm = re.sub(r"[:=]\s*", ": ", norm)

    return raw, norm


# ============================================================================
# 필드 패턴 (확장)
# ============================================================================

FIELD_PATTERNS = {
    "unit_price": [
        rf"{UNIT_PRICE_HEADERS}\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
        rf"(?:개당|단가)\s*{NUM}\s*{WON_UNIT}",
        rf"{NUM}\s*{WON_UNIT}\s*(?:/|당)\s*(?:EA|세트|대|본)?",
    ],
    "qty": [
        rf"{QTY_HEADERS}\s*[:=]?\s*{NUM}\s*{QTY_UNIT}",
        rf"{NUM}\s*{QTY_UNIT}\s*(?:{AMOUNT_HEADERS}|{UNIT_PRICE_HEADERS}|{TOTAL_HEADERS})",
        rf"{NUM}\s*{QTY_UNIT}(?:\s|$)",
    ],
    "amount": [
        # 곱셈식 우선 (예: "3 EA x 550,000원")
        rf"{NUM}\s*{QTY_UNIT}\s*{MUL}\s*{NUM}\s*{WON_UNIT}",
        rf"(?:{AMOUNT_HEADERS})\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
        rf"소계\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
    ],
    "vat": [
        rf"(?:{VAT_HEADERS})\s*(?:포함|별도)?\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
    ],
    "total": [
        # 혼합 표기 우선 (예: "총액: 1억 2,300만원")
        rf"(?:{TOTAL_HEADERS})\s*[:=]?\s*{NUM}\s*억\s*{NUM}?\s*만원",
        rf"(?:{TOTAL_HEADERS})\s*[:=]?\s*{NUM}\s*억원\s*{NUM}?\s*만원",
        rf"(?:{TOTAL_HEADERS})\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
        rf"(?:최종|결제)\s*금액\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
        rf"(?:총|전체)\s*금액\s*[:=]?\s*{NUM}\s*{WON_UNIT}",
    ],
}

# VAT 정책 플래그 패턴
INCLUDE_VAT_RE = re.compile(
    r"(부가세\s*포함|VAT\s*포함|vat\s*inc|tax\s*incl)",
    re.IGNORECASE,
)
EXCLUDE_VAT_RE = re.compile(
    r"(부가세\s*별도|VAT\s*별도|vat\s*ex|tax\s*excl)",
    re.IGNORECASE,
)
ZERO_VAT_RE = re.compile(
    r"(면세|영세|0%\s*VAT)",
    re.IGNORECASE,
)


# ============================================================================
# 매칭 유틸리티
# ============================================================================

def _first_match_with_span(
    pattern: str, text: str,
) -> Optional[tuple[str, tuple[int, int], re.Match]]:
    """패턴 매칭 + span 정보 반환

    Args:
        pattern: 정규식 패턴
        text: 검색 대상 텍스트

    Returns:
        (매칭 문자열, (start, end), Match 객체) 또는 None
    """
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    return m.group(0), (m.start(), m.end()), m


def _parse_num_and_unit(
    m: re.Match, num_group: int = 1, unit_group: int = 2,
) -> Optional[int]:
    """Match 객체에서 숫자와 단위 추출 후 정규화

    Args:
        m: Match 객체
        num_group: 숫자 그룹 인덱스
        unit_group: 단위 그룹 인덱스

    Returns:
        원 단위 정수 또는 None
    """
    try:
        num = m.group(num_group)
    except IndexError:
        return None

    # 혼합 단위 우선 처리 (예: "1억 2,300만원")
    mixed = normalize_mixed_currency(m.group(0))
    if mixed:
        return mixed

    # 단위 그룹 안전하게 추출 (없으면 None)
    try:
        unit = (m.group(unit_group) or "").strip()
    except IndexError:
        unit = None

    # 단일 단위 처리
    return normalize_currency(num, unit or "원")


# ============================================================================
# 추출 메인 함수
# ============================================================================

def extract_financial_fields(text: str) -> dict[str, Optional[int]]:
    """텍스트에서 금액 필드 추출 (개선판: 혼합 통화, 곱셈, VAT 정책, 2트랙 탐색)

    Args:
        text: 원본 문서 텍스트

    Returns:
        추출된 금액 필드 딕셔너리:
        {
            "unit_price": int or None,
            "qty": int or None,
            "amount": int or None,
            "vat": int or None,
            "total": int or None,
            "_meta": {
                "spans": Dict[str, List[int, int]],  # 근거 span
                "vat_mode": str  # "included", "excluded", "zero", "unknown"
            }
        }

    Example:
        >>> text = "총액: 1억 2,300만원 (부가세 포함)"
        >>> result = extract_financial_fields(text)
        >>> result["total"]
        123000000
        >>> result["_meta"]["vat_mode"]
        'included'
    """
    fields: dict[str, Optional[int]] = {
        "unit_price": None,
        "qty": None,
        "amount": None,
        "vat": None,
        "total": None,
    }

    # 원문/정규화문 2트랙 전처리
    raw, norm = _preprocess_dual(text)

    def search_in_both(
        pattern: str,
    ) -> Optional[tuple[str, tuple[int, int], re.Match, bool]]:
        """원문과 정규화문 모두에서 탐색 (정규화문 우선)"""
        for s, is_norm in ((norm, True), (raw, False)):
            res = _first_match_with_span(pattern, s)
            if res:
                g, span, m = res
                return g, span, m, is_norm
        return None

    # 필드별 1차 추출
    spans: dict[str, tuple[int, int]] = {}

    for field, patterns in FIELD_PATTERNS.items():
        for pat in patterns:
            found = search_in_both(pat)
            if not found:
                continue

            full, span, m, is_norm = found

            # 특수 케이스 처리
            if field == "amount" and re.search(MUL, full):
                # 곱셈식 금액 계산 (예: "3 EA x 550,000원")
                qty_str = m.group(1)
                unit_str = m.group(2)
                qty = normalize_currency(qty_str, None)
                unit = normalize_currency(unit_str, "원")

                if qty and unit:
                    fields["amount"] = qty * unit
                    spans[field] = span
                    logger.debug(
                        f"✓ amount(calc): {qty} × {unit} → {fields['amount']}",
                    )
                    break

            elif field == "total" and ("억" in full or "만원" in full):
                # 혼합 표기 총액 (예: "총액: 1억 2,300만원")
                val = normalize_mixed_currency(full)
                if val:
                    fields[field] = val
                    spans[field] = span
                    logger.debug(f"✓ total(mixed): '{full}' → {val}")
                    break

            else:
                # 일반 케이스: 숫자 + 단위 파싱
                val = _parse_num_and_unit(m)
                if val is not None:
                    fields[field] = val
                    spans[field] = span
                    logger.debug(
                        f"✓ {field}: '{full}' → {val} (norm={is_norm})",
                    )
                    break

    # 수량×단가 보간 (amount 없고 unit_price/qty 있으면 계산)
    if fields["amount"] is None and fields["unit_price"] and fields["qty"]:
        fields["amount"] = fields["unit_price"] * fields["qty"]
        logger.debug(
            f"✓ amount(backfill): unit_price×qty → {fields['amount']}",
        )

    # VAT 정책 플래그 감지
    vat_mode = "unknown"
    if ZERO_VAT_RE.search(text):
        vat_mode = "zero"
    elif INCLUDE_VAT_RE.search(text):
        vat_mode = "included"
    elif EXCLUDE_VAT_RE.search(text):
        vat_mode = "excluded"

    # 추출 결과 로깅
    extracted = {k: v for k, v in fields.items() if v is not None}
    if extracted:
        logger.info(
            f"💰 금액 필드 추출 완료: {len(extracted)}개 "
            f"({', '.join(extracted.keys())}), VAT_MODE={vat_mode}",
        )
    else:
        logger.warning("⚠️ 금액 필드 추출 실패 (패턴 매칭 없음)")

    # 근거 span 및 VAT 정책 메타데이터 포함
    fields["_meta"] = {
        "spans": {k: [v[0], v[1]] for k, v in spans.items()},
        "vat_mode": vat_mode,
    }

    return fields


# ============================================================================
# 검증 함수 (VAT 정책 분기 포함)
# ============================================================================

def validate_financial_consistency(fields: dict[str, Optional[int]]) -> dict[str, Any]:
    """금액 필드 간 일관성 검증 (개선판: VAT 정책 분기)

    Args:
        fields: extract_financial_fields() 결과

    Returns:
        검증 결과:
        {
            "is_valid": bool,
            "errors": List[str],
            "warnings": List[str]
        }

    Notes:
        - VAT 포함/면세: total ≈ amount (±1.5%)
        - VAT 별도: amount + vat ≈ total (±1.5%)
        - VAT 10% 규칙: vat ≈ amount × 0.1 (±2%)
    """
    errors: list[str] = []
    warnings: list[str] = []

    unit_price = fields.get("unit_price")
    qty = fields.get("qty")
    amount = fields.get("amount")
    vat = fields.get("vat")
    total = fields.get("total")

    # VAT 정책 플래그
    vat_mode = (fields.get("_meta") or {}).get("vat_mode", "unknown")

    # 필수: total
    if not (total and total > 0):
        errors.append("필수 필드 누락: total(총액) 없음")

    # VAT 정책별 검증 분기
    if total and amount:
        if vat_mode in ("included", "zero"):
            # 포함/면세: total ≈ amount (±1.5%)
            diff = abs(total - amount) / total
            if diff > FinanceExtractorConfig.TOTAL_AMOUNT_TOLERANCE:
                errors.append(
                    f"총액-공급가액 불일치(포함/면세): "
                    f"total={total:,}, amount={amount:,}, "
                    f"diff={diff * 100:.2f}%",
                )

        elif vat_mode in ("excluded", "unknown"):
            # 별도: amount + vat ≈ total
            if vat:
                diff = abs((amount + vat) - total) / total
                if diff > FinanceExtractorConfig.TOTAL_AMOUNT_TOLERANCE:
                    errors.append(
                        f"금액+부가세 ≠ 총액: "
                        f"{amount:,}+{vat:,}={amount + vat:,} vs {total:,} "
                        f"(diff {diff * 100:.2f}%)",
                    )
            else:
                warnings.append(
                    "부가세 별도일 가능성: vat 미검출. 문구/표 확인 필요",
                )

    # 단가×수량 vs amount (±5% 허용)
    if unit_price and qty and amount:
        calc = unit_price * qty
        diff = abs(calc - amount) / max(amount, 1)
        if diff > FinanceExtractorConfig.QTY_PRICE_TOLERANCE:
            errors.append(
                f"단가×수량 불일치: "
                f"{unit_price:,}×{qty}={calc:,} vs amount={amount:,} "
                f"(diff {diff * 100:.1f}%)",
            )

    # VAT 10% 규칙 (면세/포함 제외, ±2% 허용)
    if amount and vat and vat_mode not in ("zero", "included"):
        exp_vat = round(amount * FinanceExtractorConfig.VAT_RATE)
        diff = abs(exp_vat - vat) / max(vat, 1)
        if diff > FinanceExtractorConfig.VAT_RULE_TOLERANCE:
            warnings.append(
                f"부가세 10% 규칙 벗어남: "
                f"expected={exp_vat:,}, actual={vat:,} "
                f"(diff {diff * 100:.1f}%)",
            )

    # 최종 검증 결과
    is_valid = not errors

    if errors:
        logger.error(f"❌ 금액 검증 실패: {len(errors)}개 오류")
        for e in errors:
            logger.error(f"  - {e}")

    if warnings:
        logger.warning(f"⚠️ 금액 검증 경고: {len(warnings)}개")
        for w in warnings:
            logger.warning(f"  - {w}")

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
    }


# ============================================================================
# 통합 API
# ============================================================================

def extract_and_validate(text: str) -> dict[str, Any]:
    """금액 추출 + 검증을 한번에 수행

    Args:
        text: 원본 문서 텍스트

    Returns:
        {
            "fields": Dict[str, Optional[int]],
            "validation": Dict[str, Any]
        }

    Example:
        >>> text = "단가: 550,000원, 수량: 3 EA, 총액: 1,650,000원"
        >>> result = extract_and_validate(text)
        >>> result["validation"]["is_valid"]
        True
    """
    fields = extract_financial_fields(text)
    validation = validate_financial_consistency(fields)

    return {
        "fields": fields,
        "validation": validation,
    }


__all__ = [
    "extract_and_validate",
    "extract_financial_fields",
    "normalize_currency",
    "normalize_mixed_currency",
    "validate_financial_consistency",
]
