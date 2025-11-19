"""JSON 파싱 유틸리티 (강건한 파서)"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _mask_sensitive_data(obj: Any, max_length: int = 200) -> str:
    """민감정보 마스킹 및 샘플링

    Args:
        obj: 마스킹할 객체
        max_length: 최대 출력 길이

    Returns:
        마스킹된 문자열
    """
    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            # 금액/계정/이름 필드 마스킹
            if any(keyword in str(k).lower() for keyword in ["금액", "총액", "단가", "예산", "amount", "price"]):
                masked[k] = "***"
            elif isinstance(v, (dict, list)):
                masked[k] = f"<{type(v).__name__}>"
            else:
                masked[k] = str(v)[:50] + "..." if len(str(v)) > 50 else v
        result = json.dumps(masked, ensure_ascii=False)
        return result[:max_length] + "..." if len(result) > max_length else result
    return str(obj)[:max_length]


def _extract_balanced_json_blocks(s: str) -> List[str]:
    """문자열에서 모든 균형 잡힌 JSON 객체 블록 추출 (문자열 내부 중괄호 안전 처리)

    Args:
        s: JSON이 포함된 문자열

    Returns:
        균형 잡힌 JSON 블록 리스트
    """
    blocks = []
    depth = 0
    start = None
    in_str = False
    quote = None
    esc = False

    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        blocks.append(s[start:i + 1])

    return blocks


def extract_last_json_block(s: str) -> Dict[str, Any]:
    """마지막 균형 잡힌 {...} 블록만 추출 후 파싱 (문자열 안전)

    Args:
        s: JSON이 포함된 문자열

    Returns:
        파싱된 JSON 딕셔너리

    Raises:
        ValueError: JSON 객체를 찾을 수 없거나 파싱 실패
    """
    blocks = _extract_balanced_json_blocks(s)

    if not blocks:
        raise ValueError("No JSON object found")

    # 마지막 블록 선택
    last = blocks[-1]

    try:
        return json.loads(last)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 파싱 실패: {e}")
        raise ValueError(f"Invalid JSON: {e}") from e


def parse_summary_json_robust(response: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 추출 및 파싱 (강건한 버전)

    여러 전략을 순차적으로 시도:
    1. 코드블록 제거 (jsonc, JSONC, Jsonc 변형 지원)
    2. 균형 잡힌 모든 블록 추출 → 첫 파싱 성공
    3. 끝 콤마 제거 후 재시도
    4. raw_decode 스캔

    Args:
        response: LLM 응답 텍스트

    Returns:
        파싱된 JSON dict, 실패 시 None
    """
    try:
        # 1단계: 코드블록 제거 (변형 지원: json, jsonc, JSONC, Jsonc, Json)
        cleaned = re.sub(r"```(?:jsonc?|JSONC?|Jsonc?|Json|JSON)\s*|\s*```", "", response, flags=re.IGNORECASE).strip()

        # 2단계: 균형 잡힌 모든 {...} 블록 추출
        blocks = _extract_balanced_json_blocks(cleaned)

        # 각 블록을 순회하며 파싱 시도
        for block in blocks:
            # 3단계: 직접 파싱 시도
            try:
                parsed = json.loads(block)
                logger.info("✓ JSON 파싱 성공 (균형 블록)")
                logger.debug(f"🔍 파싱된 JSON 키: {list(parsed.keys())}")
                logger.debug(f"🔍 샘플: {_mask_sensitive_data(parsed, max_length=200)}")
                return parsed
            except json.JSONDecodeError:
                pass

            # 4단계: 끝 콤마 제거 후 재시도
            try:
                fixed_block = re.sub(r",\s*([}\]])", r"\1", block)
                parsed = json.loads(fixed_block)
                logger.info("✓ JSON 파싱 성공 (콤마 수정)")
                logger.debug(f"🔍 파싱된 JSON 키: {list(parsed.keys())}")
                logger.debug(f"🔍 샘플: {_mask_sensitive_data(parsed, max_length=200)}")
                return parsed
            except json.JSONDecodeError:
                pass

        # 5단계: raw_decode 백업 경로 (스트리밍 잔재 처리)
        decoder = json.JSONDecoder()
        i = 0
        while i < len(cleaned):
            try:
                obj, idx = decoder.raw_decode(cleaned, i)
                if isinstance(obj, dict):
                    logger.info("✓ JSON 파싱 성공 (raw_decode)")
                    logger.debug(f"🔍 파싱된 JSON 키: {list(obj.keys())}")
                    logger.debug(f"🔍 샘플: {_mask_sensitive_data(obj, max_length=200)}")
                    return obj
                i = idx + 1
            except json.JSONDecodeError:
                i += 1

        # 6단계: 모든 시도 실패
        logger.warning(f"❌ JSON 파싱 완전 실패. LLM 원문(첫 200자):\n{response[:200]}")
        return None

    except Exception as e:
        logger.error(f"❌ JSON 파싱 예외: {e}")
        return None


def ensure_citations(json_data: Dict[str, Any], doc_ref: Optional[str] = None) -> Dict[str, Any]:
    """JSON 응답에 citations 필드 확인 및 보강 (중복 방지)

    Args:
        json_data: 파싱된 JSON 데이터
        doc_ref: 참조 문서명 (있으면 강제 추가)

    Returns:
        citations 필드가 보장된 JSON 데이터
    """
    # citations 필드가 없거나 리스트가 아닌 경우 초기화
    if "citations" not in json_data or not isinstance(json_data["citations"], list):
        json_data["citations"] = []

    # 기존 citation source 세트 (중복 방지)
    existing_sources = {
        citation.get("source")
        for citation in json_data["citations"]
        if isinstance(citation, dict)
    }

    # doc_ref가 있고 중복이 아니면 추가
    if doc_ref and doc_ref not in existing_sources:
        json_data["citations"].append({
            "source": doc_ref,
            "pages": "전체",
            "confidence": "high"
        })
        logger.info(f"✓ 인용 추가: {doc_ref}")

    return json_data


def extract_amounts_from_text(text: str) -> list:
    """텍스트에서 금액 추출 (원문에서만, amount_parser_v2 사용)

    Args:
        text: 원문 텍스트

    Returns:
        추출된 금액 리스트 [(금액, 컨텍스트), ...]
    """
    from app.data.amount_parser_v2 import extract_amounts

    # amount_parser_v2를 호출 (억/만 단위 포함)
    amounts_dict = extract_amounts(text)

    # 기존 인터페이스 유지: [(금액, 컨텍스트), ...]
    return [(amt["value"], amt["context"]) for amt in amounts_dict]


def validate_numeric_fields(json_data: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    """JSON 응답의 수치 필드를 원문과 대조 검증 (근접도 기반, __validation__ 포함)

    Args:
        json_data: 파싱된 JSON 데이터
        source_text: 원문 텍스트

    Returns:
        검증된 JSON 데이터 + __validation__ 섹션
    """
    import re

    from app.core.logging import get_logger
    from app.data.amount_parser_v2 import nearest_amount_to_keyword

    logger = get_logger(__name__)

    # 원문에서 금액 추출
    source_amounts = extract_amounts_from_text(source_text)
    source_values = {amount for amount, _ in source_amounts}

    # __validation__ 초기화
    validation = {
        "source_amounts": sorted(list(source_values)),
        "actions": [],
        "confidence": {},
    }

    # 디버깅: 원문에서 추출된 금액 로깅
    logger.info(f"📊 원문에서 추출된 금액: {sorted(source_values)}")

    # 1. 구매/소모품 문서 ("details" 필드)
    if "details" in json_data and "금액" in json_data["details"]:
        claimed_amount_str = json_data["details"]["금액"]
        try:
            claimed_amount = int(re.sub(r"[^\d]", "", str(claimed_amount_str)))
            if claimed_amount in source_values:
                # 유지
                validation["actions"].append({
                    "field": "details.금액",
                    "action": "keep",
                    "value": claimed_amount,
                    "reason": "exact_match_in_source",
                })
                validation["confidence"]["details.금액"] = 1.0
            else:
                # 근접도 기반 교정 시도
                nearest = nearest_amount_to_keyword(source_text, ["금액", "총액", "합계"])
                if nearest:
                    correct_amount = nearest["value"]
                    logger.warning(f"⚠️ 금액 교정 (근접도): {claimed_amount} → {correct_amount} (confidence: {nearest['confidence']:.2f})")
                    json_data["details"]["금액"] = correct_amount
                    validation["actions"].append({
                        "field": "details.금액",
                        "action": "correct",
                        "from": claimed_amount,
                        "to": correct_amount,
                        "reason": "nearest_keyword",
                    })
                    validation["confidence"]["details.금액"] = nearest["confidence"]
                else:
                    logger.warning(f"⚠️ 원문에 없는 금액 제거: {claimed_amount}")
                    json_data["details"]["금액"] = "정보 없음"
                    validation["actions"].append({
                        "field": "details.금액",
                        "action": "remove",
                        "from": claimed_amount,
                        "reason": "not_found_in_source",
                    })
                    validation["confidence"]["details.금액"] = 0.0
        except (ValueError, TypeError):
            pass

    # 2. 수리 문서 ("비용상세" 필드)
    if "비용상세" in json_data:
        cost_detail = json_data["비용상세"]

        # 총액 검증 (근접도 기반)
        if "총액" in cost_detail:
            claimed_total_str = str(cost_detail["총액"])
            try:
                claimed_total = int(re.sub(r"[^\d]", "", claimed_total_str))

                if claimed_total in source_values:
                    # 유지
                    validation["actions"].append({
                        "field": "비용상세.총액",
                        "action": "keep",
                        "value": claimed_total,
                        "reason": "exact_match_in_source",
                    })
                    validation["confidence"]["비용상세.총액"] = 1.0
                else:
                    # 근접도 기반 교정 (총액/합계 키워드)
                    nearest = nearest_amount_to_keyword(
                        source_text,
                        ["총액", "합계", "총금액", "총 액"],
                        prefer_later=True  # 문서 후반부 우선 (결론부)
                    )
                    if nearest:
                        correct_total = nearest["value"]
                        logger.warning(f"⚠️ 총액 교정 (근접도): {claimed_total} → {correct_total} (confidence: {nearest['confidence']:.2f})")
                        json_data["비용상세"]["총액"] = correct_total
                        validation["actions"].append({
                            "field": "비용상세.총액",
                            "action": "correct",
                            "from": claimed_total,
                            "to": correct_total,
                            "reason": "nearest_total_keyword",
                        })
                        validation["confidence"]["비용상세.총액"] = nearest["confidence"]
                    else:
                        logger.warning(f"⚠️ 원문에 없는 총액 제거: {claimed_total}")
                        json_data["비용상세"]["총액"] = "정보 없음"
                        validation["actions"].append({
                            "field": "비용상세.총액",
                            "action": "remove",
                            "from": claimed_total,
                            "reason": "not_found_in_source",
                        })
                        validation["confidence"]["비용상세.총액"] = 0.0
            except (ValueError, TypeError):
                pass

        # 단가 검증 (근접도 기반)
        if "단가" in cost_detail:
            claimed_unit_str = str(cost_detail["단가"])
            try:
                claimed_unit = int(re.sub(r"[^\d]", "", claimed_unit_str))

                if claimed_unit in source_values:
                    # 유지
                    validation["actions"].append({
                        "field": "비용상세.단가",
                        "action": "keep",
                        "value": claimed_unit,
                        "reason": "exact_match_in_source",
                    })
                    validation["confidence"]["비용상세.단가"] = 1.0
                else:
                    # 근접도 기반 교정 (단가 키워드)
                    nearest = nearest_amount_to_keyword(
                        source_text,
                        ["단가", "단위가격", "단위 가격"],
                        prefer_later=False  # 선언부 우선
                    )
                    if nearest:
                        correct_unit = nearest["value"]
                        logger.warning(f"⚠️ 단가 교정 (근접도): {claimed_unit} → {correct_unit} (confidence: {nearest['confidence']:.2f})")
                        json_data["비용상세"]["단가"] = f"{correct_unit:,}원"
                        validation["actions"].append({
                            "field": "비용상세.단가",
                            "action": "correct",
                            "from": claimed_unit,
                            "to": correct_unit,
                            "reason": "nearest_unit_keyword",
                        })
                        validation["confidence"]["비용상세.단가"] = nearest["confidence"]
                    else:
                        logger.warning(f"⚠️ 원문에 없는 단가: {claimed_unit} (유지)")
                        validation["actions"].append({
                            "field": "비용상세.단가",
                            "action": "keep",
                            "value": claimed_unit,
                            "reason": "ambiguous_no_correction",
                        })
                        validation["confidence"]["비용상세.단가"] = 0.5
            except (ValueError, TypeError):
                pass

    # 3. 검토서 문서 ("예산합계" 필드)
    if "예산합계" in json_data:
        budget_str = str(json_data["예산합계"])
        try:
            budget = int(re.sub(r"[^\d]", "", budget_str))
            if budget in source_values:
                # 유지
                validation["actions"].append({
                    "field": "예산합계",
                    "action": "keep",
                    "value": budget,
                    "reason": "exact_match_in_source",
                })
                validation["confidence"]["예산합계"] = 1.0
            else:
                # 근접도 기반 교정
                nearest = nearest_amount_to_keyword(source_text, ["예산", "예산합계", "총예산"])
                if nearest:
                    correct_budget = nearest["value"]
                    logger.warning(f"⚠️ 예산 교정 (근접도): {budget} → {correct_budget} (confidence: {nearest['confidence']:.2f})")
                    json_data["예산합계"] = correct_budget
                    validation["actions"].append({
                        "field": "예산합계",
                        "action": "correct",
                        "from": budget,
                        "to": correct_budget,
                        "reason": "nearest_budget_keyword",
                    })
                    validation["confidence"]["예산합계"] = nearest["confidence"]
                else:
                    logger.warning(f"⚠️ 원문에 없는 예산 제거: {budget}")
                    json_data["예산합계"] = "정보 없음"
                    validation["actions"].append({
                        "field": "예산합계",
                        "action": "remove",
                        "from": budget,
                        "reason": "not_found_in_source",
                    })
                    validation["confidence"]["예산합계"] = 0.0
        except (ValueError, TypeError):
            pass

    # __validation__ 섹션 추가
    json_data["__validation__"] = validation

    return json_data
