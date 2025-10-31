"""금액·표 추출 모듈 (deterministic extractor)

정규표현식 기반 금액 필드 추출기
LLM은 구조 재구성 및 인용만 담당, 계산은 하지 않음
"""

import re
from typing import Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


# 금액 패턴 (숫자 + 쉼표)
NUM = r"([\d,]+)"

# 원화 단위 (원, 만원, 억원)
WON = r"\s*(?:원|만원|억원|KRW|₩)?"


# 필드별 정규표현식 패턴
FIELD_PATTERNS = {
    "unit_price": [
        rf"단가\s*[:=]?\s*{NUM}{WON}",
        rf"품목.*단가\s*[:=]?\s*{NUM}{WON}",
        rf"개당\s*{NUM}{WON}",
    ],
    "qty": [
        rf"수량\s*[:=]?\s*{NUM}\s*(?:개|EA|ea|SET|set)?",
        rf"발주\s*수량\s*[:=]?\s*{NUM}",
        rf"{NUM}\s*(?:개|EA|ea)(?:\s|$)",
    ],
    "amount": [
        rf"(?:공급|금액|품목.*금액)\s*[:=]?\s*{NUM}{WON}",
        rf"소계\s*[:=]?\s*{NUM}{WON}",
    ],
    "vat": [
        rf"(?:부가세|부가가치세|VAT|세액)\s*[:=]?\s*{NUM}{WON}",
        rf"세\s*액\s*[:=]?\s*{NUM}{WON}",
    ],
    "total": [
        rf"(?:총액|합계|총\s?계|계)\s*[:=]?\s*{NUM}{WON}",
        rf"(?:최종|결제)\s*금액\s*[:=]?\s*{NUM}{WON}",
        rf"(?:총|전체)\s*금액\s*[:=]?\s*{NUM}{WON}",
    ],
}


def _parse_number(num_str: str) -> Optional[int]:
    """숫자 문자열을 정수로 파싱 (쉼표 제거)

    Args:
        num_str: 숫자 문자열 (예: "1,200,000")

    Returns:
        정수 값 또는 None
    """
    try:
        # 쉼표 제거 후 정수 변환
        cleaned = num_str.replace(",", "").strip()
        return int(cleaned)
    except (ValueError, AttributeError):
        return None


def _preprocess_table_text(text: str) -> str:
    """OCR 텍스트 표 구조 전처리 (패치 AC2-S1)

    Args:
        text: 원본 OCR 텍스트

    Returns:
        전처리된 텍스트
    """
    # 1. 줄바꿈 + 다중 공백 정리
    text = re.sub(r'\s+', ' ', text)

    # 2. 단위 분리 보정 (숫자와 단위 사이에 공백 추가)
    text = re.sub(r'(\d)(원|만원|억원|개|EA|ea)', r'\1 \2', text)

    # 3. 열 머리글 근접 탐색 윈도우 생성 (수량/단가/금액 키워드 주변 ±100자)
    table_keywords = ['수량', '단가', '금액', '품목', '총액', '합계', 'VAT', '부가세']
    enhanced_sections = []

    for keyword in table_keywords:
        # 키워드 주변 ±100자 추출
        for match in re.finditer(keyword, text, re.IGNORECASE):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            enhanced_sections.append(text[start:end])

    # 4. 원본 + 강화 섹션 결합
    return text + ' ' + ' '.join(enhanced_sections)


def extract_financial_fields(text: str) -> Dict[str, Optional[int]]:
    """텍스트에서 금액 필드 추출 (deterministic, 패치 AC2-S1 표 전처리 적용)

    Args:
        text: 원본 문서 텍스트

    Returns:
        추출된 금액 필드 딕셔너리:
        {
            "unit_price": int or None,
            "qty": int or None,
            "amount": int or None,
            "vat": int or None,
            "total": int or None
        }
    """
    results = {
        "unit_price": None,
        "qty": None,
        "amount": None,
        "vat": None,
        "total": None,
    }

    # 패치 AC2-S1: OCR 텍스트 표 전처리
    text = _preprocess_table_text(text)

    # 각 필드별로 패턴 매칭 시도
    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                # 첫 번째 그룹이 숫자
                num_str = match.group(1)
                parsed = _parse_number(num_str)
                if parsed is not None:
                    results[field] = parsed
                    logger.debug(f"✓ {field} 추출: {num_str} → {parsed}")
                    break  # 첫 매칭만 사용

    # 추출 결과 로깅
    extracted = {k: v for k, v in results.items() if v is not None}
    if extracted:
        logger.info(f"💰 금액 필드 추출 완료: {len(extracted)}개 필드 ({', '.join(extracted.keys())})")
    else:
        logger.warning("⚠️ 금액 필드 추출 실패 (패턴 매칭 없음)")

    return results


def validate_financial_consistency(fields: Dict[str, Optional[int]]) -> Dict[str, any]:
    """금액 필드 간 일관성 검증 (패치 AC2-S1: 필수 필드 검증 강화)

    Args:
        fields: extract_financial_fields() 결과

    Returns:
        검증 결과:
        {
            "is_valid": bool,
            "errors": List[str],
            "warnings": List[str]
        }
    """
    errors = []
    warnings = []

    unit_price = fields.get("unit_price")
    qty = fields.get("qty")
    amount = fields.get("amount")
    vat = fields.get("vat")
    total = fields.get("total")

    # 패치 AC2-S1: 필수 필드 검증 강화
    # 옵션 B(권고): total 존재 + (amount OR unit_price×qty) 중 하나 일치
    has_total = total is not None and total > 0
    has_amount = amount is not None and amount > 0
    has_unit_qty = unit_price is not None and qty is not None and qty > 0

    # 최소 요건: total이 있어야 함
    if not has_total:
        errors.append("필수 필드 누락: total(총액) 필드가 없습니다")

    # total이 있으면 amount 또는 unit_price×qty 중 하나는 있어야 함
    if has_total and not (has_amount or has_unit_qty):
        warnings.append("검증 제한: amount 또는 (unit_price × qty) 중 하나가 필요합니다")

    # 검증 1: unit_price * qty == amount (±5% 허용)
    if unit_price and qty and amount:
        calculated = unit_price * qty
        diff_pct = abs(calculated - amount) / amount if amount > 0 else 0
        if diff_pct > 0.05:
            errors.append(
                f"단가×수량 불일치: {unit_price} × {qty} = {calculated}, "
                f"but amount={amount} (차이 {diff_pct*100:.1f}%)"
            )

    # 검증 2: amount + vat == total (±1% 허용)
    if amount and vat and total:
        calculated_total = amount + vat
        diff_pct = abs(calculated_total - total) / total if total > 0 else 0
        if diff_pct > 0.01:
            errors.append(
                f"금액+부가세 불일치: {amount} + {vat} = {calculated_total}, "
                f"but total={total} (차이 {diff_pct*100:.1f}%)"
            )

    # 검증 3: vat == amount * 0.1 (±1% 허용)
    if amount and vat:
        calculated_vat = int(amount * 0.1)
        diff_pct = abs(calculated_vat - vat) / vat if vat > 0 else 0
        if diff_pct > 0.01:
            warnings.append(
                f"부가세 비율 경고: amount={amount}이면 VAT={calculated_vat} 예상, "
                f"but vat={vat} (차이 {diff_pct*100:.1f}%)"
            )

    # 최종 검증 결과 (패치 AC2-S1: 엄격한 검증)
    is_valid = len(errors) == 0

    if errors:
        logger.error(f"❌ 금액 필드 검증 실패: {len(errors)}개 오류")
        for err in errors:
            logger.error(f"  - {err}")

    if warnings:
        logger.warning(f"⚠️ 금액 필드 검증 경고: {len(warnings)}개")
        for warn in warnings:
            logger.warning(f"  - {warn}")

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings
    }


def extract_and_validate(text: str) -> Dict[str, any]:
    """금액 추출 + 검증을 한번에 수행

    Args:
        text: 원본 문서 텍스트

    Returns:
        {
            "fields": Dict[str, Optional[int]],
            "validation": Dict[str, any]
        }
    """
    fields = extract_financial_fields(text)
    validation = validate_financial_consistency(fields)

    return {
        "fields": fields,
        "validation": validation
    }
