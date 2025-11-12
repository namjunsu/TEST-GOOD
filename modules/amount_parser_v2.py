#!/usr/bin/env python3
"""
강화된 금액 파서 v2.1
- 상/하한 가드
- 테이블 라인아이템 우선 처리
- 문서 단위 스코프 보장
- 억/만 단위 혼합 표기 지원
- 키워드 근접도 기반 랭킹
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

# 한국어 통화 표기 포괄 (₩/원/콤마/공백/마침표/OCR 흔적)
RE_KRW = re.compile(r"""
    (?<!\d)
    (?:₩\s*)?
    (?:\d{1,3}(?:[,.\s]\d{3})+|\d{4,})
    \s*(?:원)?
""", re.VERBOSE)

# 억/만 단위 패턴 (콤마 지원)
RE_EOK_MAN = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*억(?:\s*([\d,]+(?:\.\d+)?)\s*만)?",
    re.IGNORECASE
)
RE_MAN_ONLY = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*만(?![가-힣\w])",
    re.IGNORECASE
)

# 라인아이템 패턴: "333,000원 × 2EA", "380000 원 x 4"
ITEM_PAT = re.compile(
    r"(?P<price>(?:₩\s*)?(?:\d{1,3}(?:[,.\s]\d{3})+|\d{4,})\s*(?:원)?)\s*[x×＊]\s*(?P<qty>\d+)\s*(EA|대)?",
    re.IGNORECASE
)


@dataclass
class AmountCandidate:
    raw: str
    value: int
    start: int
    end: int
    context: str
    kind: str = "krw"  # krw, eok, man, eok+man


def _to_int_krw(token: str) -> Optional[int]:
    """숫자 문자열을 정수로 변환 (공백/콤마/마침표/'원' 제거)"""
    t = token.replace("₩", "").replace("원", "")
    t = re.sub(r"[\s,\.]", "", t)
    return int(t) if t.isdigit() else None


def _parse_eok_man(text: str) -> List[Tuple[int, int, int, str]]:
    """억/만 단위 파싱 (콤마 지원)

    Args:
        text: 원문 텍스트

    Returns:
        [(value, start, end, kind), ...]
    """
    results = []

    # 1) x억 y만
    for m in RE_EOK_MAN.finditer(text):
        eok_str = m.group(1).replace(",", "")  # 콤마 제거
        man_str = (m.group(2) or "0").replace(",", "")  # 콤마 제거
        try:
            eok = float(eok_str)
            man = float(man_str)
            value = int(round(eok * 100_000_000 + man * 10_000))
            kind = "eok+man" if man > 0 else "eok"
            results.append((value, m.start(), m.end(), kind))
        except (ValueError, TypeError):
            continue

    # 2) x만 (단독, 억 뒤가 아닌 경우)
    for m in RE_MAN_ONLY.finditer(text):
        # 이미 억+만으로 처리된 범위는 스킵 (중복 방지)
        overlapped = any(
            start <= m.start() < end
            for _, start, end, _ in results
        )
        if overlapped:
            continue

        man_str = m.group(1).replace(",", "")  # 콤마 제거
        try:
            man = float(man_str)
            value = int(round(man * 10_000))
            results.append((value, m.start(), m.end(), "man"))
        except (ValueError, TypeError):
            continue

    return results


def format_krw(value: Optional[int]) -> str:
    """금액 포맷팅 (천 단위 콤마 + 원)

    Args:
        value: 금액 (None이면 "정보 없음")

    Returns:
        포맷된 문자열
    """
    if value is None:
        return "정보 없음"
    return f"{value:,}원"


def extract_amount_candidates(text: str, window: int = 30) -> List[AmountCandidate]:
    """텍스트에서 금액 후보 추출 (문맥 포함, 억/만 포함)

    Args:
        text: 원문 텍스트
        window: 컨텍스트 윈도우 크기

    Returns:
        AmountCandidate 리스트 (중복 제거됨)
    """
    out: List[AmountCandidate] = []

    # 1) 억/만 단위 우선 처리
    for value, s, e, kind in _parse_eok_man(text):
        if value < 1000:  # 1000원 미만 제외
            continue
        ctx = text[max(0, s - window): min(len(text), e + window)]
        raw = text[s:e]
        out.append(AmountCandidate(raw, value, s, e, ctx, kind))

    # 2) 콤마/원 표기
    for m in RE_KRW.finditer(text):
        raw = m.group(0)
        val = _to_int_krw(raw)
        if val is None or val < 1000:
            continue

        s, e = m.start(), m.end()

        # 이미 억/만으로 처리된 범위는 스킵 (중복 방지)
        overlapped = any(
            start <= s < end
            for cand in out
            for start, end in [(cand.start, cand.end)]
        )
        if overlapped:
            continue

        ctx = text[max(0, s - window): min(len(text), e + window)]
        out.append(AmountCandidate(raw, val, s, e, ctx, "krw"))

    # 3) 중복 제거: (value, start) 기준 유니크
    seen = set()
    unique = []
    for cand in out:
        key = (cand.value, cand.start)
        if key not in seen:
            seen.add(key)
            unique.append(cand)

    return unique


def extract_line_items(text: str) -> List[Tuple[int, int]]:
    """라인아이템 추출: (unit_price, quantity)"""
    items: List[Tuple[int, int]] = []
    for m in ITEM_PAT.finditer(text):
        price = _to_int_krw(m.group("price"))
        qty_str = m.group("qty")
        try:
            qty = int(qty_str)
        except (ValueError, TypeError):
            continue

        # 검증: 단가 10,000 ~ 5,000,000원, 수량 1~50
        if price is not None and 10_000 <= price <= 5_000_000 and 1 <= qty <= 50:
            items.append((price, qty))
            logger.debug(f"Line item found: {price:,}원 × {qty} = {price * qty:,}원")

    return items


def choose_total_by_line_items(line_items: List[Tuple[int, int]]) -> Optional[int]:
    """라인아이템 기반 총액 계산 (정상 범위 검증)"""
    if not line_items:
        return None

    total = sum(u * q for (u, q) in line_items)

    # DVR 2~6대 + HDD/컨버터 포함 예상 범위
    if 100_000 <= total <= 50_000_000:
        logger.info(f"Line items total: ₩{total:,} (validated)")
        return total
    else:
        logger.warning(f"Line items total ₩{total:,} out of range, rejected")
        return None


def select_document_amount(doc_id: str, text: str, item_hint: str = "") -> Optional[int]:
    """
    문서 단위 금액 추출 (우선순위)
    1) 테이블/라인아이템 총액
    2) 자유 텍스트 금액 (정상 범위 내 중앙값)
    """
    logger.info(f"Extracting amount for doc_id={doc_id}, hint={item_hint}")

    # 1) 라인아이템 우선
    line_items = extract_line_items(text)
    if line_items:
        total = choose_total_by_line_items(line_items)
        if total is not None:
            logger.info(f"Amount from line items: ₩{total:,}")
            return total

    # 2) 자유 텍스트 후보 (억 단위/비정상 제거)
    cands = extract_amount_candidates(text)

    # 10,000 ~ 10,000,000원 범위만 수용
    normals = [c.value for c in cands if 10_000 <= c.value < 10_000_000]

    if normals:
        normals.sort()
        median = normals[len(normals) // 2]
        logger.info(f"Amount from free text (median): ₩{median:,} from {len(normals)} candidates")
        return median

    # 3) 끝까지 실패
    logger.warning(f"No valid amount found for doc_id={doc_id}")
    return None


def validate_amount(amount: Optional[int], context: str = "") -> Tuple[Optional[int], bool]:
    """
    금액 검증 (최종 가드)
    Returns: (validated_amount, is_valid)
    """
    if amount is None:
        return None, False

    # 억 단위 이상 거부
    if amount >= 100_000_000:
        logger.error(f"Amount ₩{amount:,} rejected: >= 100M (context: {context})")
        return None, False

    # 1,000원 미만 거부
    if amount < 1_000:
        logger.error(f"Amount ₩{amount:,} rejected: < 1,000 (context: {context})")
        return None, False

    return amount, True


# ============================================================================
# 공개 API (Phase 2)
# ============================================================================


@lru_cache(maxsize=512)
def extract_amounts(text: str) -> List[Dict[str, Any]]:
    """텍스트에서 모든 금액 추출 (억/만 포함, 캐시됨)

    Args:
        text: 원문 텍스트

    Returns:
        [{"value": int, "start": int, "end": int, "context": str, "kind": str}, ...]
    """
    candidates = extract_amount_candidates(text, window=40)
    return [
        {
            "value": c.value,
            "start": c.start,
            "end": c.end,
            "context": c.context,
            "kind": c.kind,
        }
        for c in candidates
    ]


def nearest_amount_to_keyword(
    text: str,
    keywords: List[str],
    window: int = 80,
    prefer_later: bool = True,
) -> Optional[Dict[str, Any]]:
    """키워드 주변 가장 가까운 금액 1건 반환 (근접도 기반 랭킹)

    Args:
        text: 원문 텍스트
        keywords: 키워드 리스트 (예: ["총액", "합계", "견적"])
        window: 키워드 주변 윈도우 크기 (기본 ±80자)
        prefer_later: True이면 문서 후반부 우선(결론부), False이면 선언부 우선

    Returns:
        {"value": int, "start": int, "end": int, "context": str, "kind": str, "distance": int, "confidence": float}
        또는 None (키워드 주변에 금액이 없음)
    """
    candidates = extract_amount_candidates(text, window=40)
    if not candidates:
        return None

    # 키워드 위치 찾기
    keyword_positions = []
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, re.IGNORECASE):
            keyword_positions.append((m.start(), kw))

    if not keyword_positions:
        logger.debug(f"No keywords found: {keywords}")
        return None

    # 각 후보에 대해 가장 가까운 키워드까지 거리 계산
    scored = []
    for cand in candidates:
        min_distance = float("inf")
        closest_kw = None

        for kw_pos, kw_text in keyword_positions:
            # 키워드 → 금액 거리 (절댓값)
            distance = abs(cand.start - kw_pos)
            if distance < min_distance:
                min_distance = distance
                closest_kw = kw_text

        # 윈도우 밖은 제외
        if min_distance > window:
            continue

        # 점수: 거리 역수 (가까울수록 높음)
        # 키워드 가중치: 총액/합계 > 금액 > 단가
        keyword_weight = 1.0
        if closest_kw and "총액" in closest_kw or "합계" in closest_kw:
            keyword_weight = 1.5
        elif closest_kw and "단가" in closest_kw:
            keyword_weight = 0.8

        score = keyword_weight / (1 + min_distance)

        # prefer_later: 문서 위치 가중치 (후반부 +10%)
        position_weight = 1.0
        if prefer_later:
            position_weight = 1.0 + (cand.start / len(text)) * 0.1
        else:
            position_weight = 1.0 + ((len(text) - cand.start) / len(text)) * 0.1

        final_score = score * position_weight

        scored.append({
            "value": cand.value,
            "start": cand.start,
            "end": cand.end,
            "context": cand.context,
            "kind": cand.kind,
            "distance": min_distance,
            "confidence": min(final_score, 1.0),
        })

    if not scored:
        return None

    # 최고 점수 반환
    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return scored[0]


# 테스트용 샘플
if __name__ == "__main__":
    test_text = """
    총액: 2,446,000원

    DVR:        333,000원 × 2EA =    666,000원
    HDD:        380,000원 × 4EA =  1,520,000원
    CONVERTER:  130,000원 × 2EA =    260,000원
    """

    amt = select_document_amount("test_001", test_text, "DVR 교체")
    if amt:
        print(f"✓ 추출 성공: ₩{amt:,}")
        validated, ok = validate_amount(amt, "DVR 교체")
        print(f"✓ 검증: {ok}, 최종 금액: ₩{validated:,}" if validated else "✗ 검증 실패")
    else:
        print("✗ 추출 실패")
