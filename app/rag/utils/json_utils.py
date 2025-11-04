"""JSON 파싱 유틸리티 (강건한 파서)"""
import json
import re
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def extract_last_json_block(s: str) -> Dict[str, Any]:
    """마지막 균형 잡힌 {...} 블록만 추출 후 파싱

    Args:
        s: JSON이 포함된 문자열

    Returns:
        파싱된 JSON 딕셔너리

    Raises:
        ValueError: JSON 객체를 찾을 수 없거나 파싱 실패
    """
    stack = []
    start = None
    last = None

    # 균형 잡힌 마지막 {...} 블록 찾기
    for i, ch in enumerate(s):
        if ch == '{':
            if not stack:
                start = i
            stack.append('{')
        elif ch == '}' and stack:
            stack.pop()
            if not stack and start is not None:
                last = s[start:i+1]

    if not last:
        raise ValueError("No JSON object found")

    try:
        return json.loads(last)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 파싱 실패: {e}")
        raise ValueError(f"Invalid JSON: {e}")


def parse_summary_json_robust(response: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 추출 및 파싱 (강건한 버전)

    여러 전략을 순차적으로 시도:
    1. 정규식으로 코드 블록 제거 후 파싱
    2. extract_last_json_block 사용
    3. 끝 콤마 제거 후 재시도

    Args:
        response: LLM 응답 텍스트

    Returns:
        파싱된 JSON dict, 실패 시 None
    """
    try:
        # 1단계: ```json ... ``` 블록 제거
        cleaned = re.sub(r"```json|```", "", response).strip()

        # 2단계: 첫 번째 {...} 블록 추출
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            json_str = match.group(0)

            # 3단계: JSON 파싱 시도
            try:
                parsed = json.loads(json_str)
                logger.info("✓ JSON 파싱 성공 (기본 방법)")
                return parsed
            except json.JSONDecodeError:
                pass

            # 4단계: 흔한 JSON 오류 수정 시도 (끝 콤마 제거)
            try:
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                parsed = json.loads(json_str)
                logger.info("✓ JSON 파싱 성공 (콤마 수정)")
                return parsed
            except json.JSONDecodeError:
                pass

        # 5단계: extract_last_json_block 시도
        try:
            parsed = extract_last_json_block(response)
            logger.info("✓ JSON 파싱 성공 (마지막 블록 추출)")
            return parsed
        except ValueError:
            pass

        # 6단계: 모든 시도 실패
        logger.warning(f"❌ JSON 파싱 완전 실패. LLM 원문(첫 800자):\n{response[:800]}")
        return None

    except Exception as e:
        logger.error(f"❌ JSON 파싱 예외: {e}")
        return None


def ensure_citations(json_data: Dict[str, Any], doc_ref: str = None) -> Dict[str, Any]:
    """JSON 응답에 citations 필드 확인 및 보강

    Args:
        json_data: 파싱된 JSON 데이터
        doc_ref: 참조 문서명 (있으면 강제 추가)

    Returns:
        citations 필드가 보장된 JSON 데이터
    """
    if "citations" not in json_data:
        json_data["citations"] = []

    # doc_ref가 있고 citations가 비어있으면 추가
    if doc_ref and not json_data["citations"]:
        json_data["citations"].append({
            "source": doc_ref,
            "pages": "전체",
            "confidence": "high"
        })
        logger.info(f"✓ 인용 강제 추가: {doc_ref}")

    return json_data


def extract_amounts_from_text(text: str) -> list:
    """텍스트에서 금액 추출 (원문에서만)

    Args:
        text: 원문 텍스트

    Returns:
        추출된 금액 리스트 [(금액, 컨텍스트), ...]
    """
    import re

    amounts = []

    # 다양한 금액 패턴 (우선순위 순서)
    patterns = [
        # 총액, 합계 (가장 중요)
        r'(?:총액|합계|총금액|총\s*액)[:\s]*([\d,]+)',
        # 단가 (명시적)
        r'(?:단가|단위\s*가격)[:\s]*([\d,]+)',
        # 금액 (일반)
        r'금액[:\s]*([\d,]+)',
        # ₩1,234,567 형태
        r'₩\s*([\d,]+)',
        # 1,234,567원 형태
        r'([\d,]+)\s*원',
        # 숫자만 (천 단위 구분 있음, 만원 이상)
        r'\b(\d{1,3}(?:,\d{3})+)\b',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            amount_str = match.group(1).replace(',', '')
            try:
                amount = int(amount_str)
                # 금액 주변 컨텍스트 추출 (앞뒤 20자)
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end].strip()
                amounts.append((amount, context))
            except ValueError:
                pass

    # 중복 제거 (같은 금액)
    seen = set()
    unique_amounts = []
    for amount, context in amounts:
        if amount not in seen:
            seen.add(amount)
            unique_amounts.append((amount, context))

    return unique_amounts


def validate_numeric_fields(json_data: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    """JSON 응답의 수치 필드를 원문과 대조 검증

    Args:
        json_data: 파싱된 JSON 데이터
        source_text: 원문 텍스트

    Returns:
        검증된 JSON 데이터 (원문에 없는 수치는 제거 또는 교정)
    """
    import re
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    # 원문에서 금액 추출
    source_amounts = extract_amounts_from_text(source_text)
    source_values = {amount for amount, _ in source_amounts}

    # 디버깅: 원문에서 추출된 금액 로깅
    logger.info(f"📊 원문에서 추출된 금액: {sorted(source_values)}")

    # 1. 구매/소모품 문서 ("details" 필드)
    if "details" in json_data and "금액" in json_data["details"]:
        claimed_amount_str = json_data["details"]["금액"]
        try:
            claimed_amount = int(re.sub(r'[^\d]', '', str(claimed_amount_str)))
            if claimed_amount not in source_values:
                logger.warning(f"⚠️ 원문에 없는 금액 제거: {claimed_amount}")
                json_data["details"]["금액"] = "정보 없음"
        except (ValueError, TypeError):
            pass

    # 2. 수리 문서 ("비용상세" 필드)
    if "비용상세" in json_data:
        cost_detail = json_data["비용상세"]

        # 총액 검증
        if "총액" in cost_detail:
            claimed_total_str = str(cost_detail["총액"])
            try:
                claimed_total = int(re.sub(r'[^\d]', '', claimed_total_str))

                if claimed_total not in source_values:
                    # 원문에서 총액/합계 키워드로 재검색
                    total_pattern = r'(?:총액|합계|총\s*액)[:\s]*([\d,]+)'
                    total_matches = re.findall(total_pattern, source_text)
                    if total_matches:
                        correct_total = int(total_matches[-1].replace(',', ''))  # 마지막 총액 사용
                        logger.warning(f"⚠️ 금액 교정: {claimed_total} → {correct_total}")
                        json_data["비용상세"]["총액"] = correct_total
                    else:
                        logger.warning(f"⚠️ 원문에 없는 총액 제거: {claimed_total}")
                        json_data["비용상세"]["총액"] = "정보 없음"
            except (ValueError, TypeError):
                pass

        # 단가 검증
        if "단가" in cost_detail:
            claimed_unit_str = str(cost_detail["단가"])
            try:
                claimed_unit = int(re.sub(r'[^\d]', '', claimed_unit_str))

                if claimed_unit not in source_values:
                    # 원문에서 단가 키워드로 재검색
                    unit_pattern = r'(?:단가|단위\s*가격)[:\s]*([\d,]+)'
                    unit_matches = re.findall(unit_pattern, source_text)
                    if unit_matches:
                        correct_unit = int(unit_matches[0].replace(',', ''))
                        logger.warning(f"⚠️ 단가 교정: {claimed_unit} → {correct_unit}")
                        json_data["비용상세"]["단가"] = f"{correct_unit:,}원"
                    else:
                        logger.warning(f"⚠️ 원문에 없는 단가: {claimed_unit} (유지)")
            except (ValueError, TypeError):
                pass

    # 3. 검토서 문서 ("예산합계" 필드)
    if "예산합계" in json_data:
        budget_str = str(json_data["예산합계"])
        try:
            budget = int(re.sub(r'[^\d]', '', budget_str))
            if budget not in source_values:
                logger.warning(f"⚠️ 원문에 없는 예산 제거: {budget}")
                json_data["예산합계"] = "정보 없음"
        except (ValueError, TypeError):
            pass

    return json_data