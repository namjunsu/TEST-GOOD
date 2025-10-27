"""
문서 유형별 요약 프롬프트 템플릿
2025-10-27

목적: 문서 타입(doctype)에 맞는 맞춤 프롬프트로 요약 품질 향상
"""

from typing import Dict, Any
import json


def get_summary_prompt(
    doctype: str,
    filename: str,
    display_date: str,
    claimed_total: int,
    context_text: str
) -> tuple[str, str]:
    """문서 유형별 요약 프롬프트 반환

    Args:
        doctype: 문서 유형 (proposal, review, minutes 등)
        filename: 파일명
        display_date: 날짜
        claimed_total: 금액 (있으면 숫자, 없으면 None)
        context_text: 문서 내용 (RAG 청크 + PDF 끝부분)

    Returns:
        tuple: (system_prompt, user_prompt)
    """

    # 공통 시스템 프롬프트
    system_prompt = """너는 회사 내부 문서를 과장 없이 정확히 요약하는 보조자다.
문서에 없는 내용은 "없음"이라고 적어라.
추측하거나 일반론으로 채우지 말 것."""

    # 기술검토서 (proposal, review)
    if doctype in ["proposal", "review", "기술검토서"]:
        user_prompt = f"""아래 문서 내용을 토대로 "기술검토서 핵심 정보"를 JSON으로만 반환해줘.
문서에 없는 값은 null 또는 "없음"으로 둬.

**문서명**: {filename}
**문서유형**: {doctype}
**날짜**: {display_date}
**합계금액**: {f"₩{claimed_total:,}" if claimed_total else "null"}

[문서 내용]
{context_text}

**JSON 스키마**:
{{
  "문서한줄요약": "한 문장으로 핵심 요약",
  "문제": "어떤 문제가 발생했는가",
  "검토제품": [
    {{"모델": "제품명", "사양": "주요 사양", "가격": "가격 정보"}},
    ...
  ],
  "선정제품": {{"모델": "최종 선택 제품", "선정이유": "선택 이유"}},
  "예산": {claimed_total if claimed_total else "null"},
  "결론": "최종 조치/결정 사항",
  "주의": "모호하거나 불확실한 부분이 있으면 이유를 명시"
}}

**주의사항**:
- 문장 반복 금지, 중복 금지
- "없음"이나 null을 허용. 절대 추정하지 말 것
- 800자 이내
- JSON만 반환 (다른 설명 금지)"""

    # 회의록 (minutes)
    elif doctype in ["minutes", "회의록"]:
        user_prompt = f"""아래 회의록 내용을 토대로 핵심 정보를 JSON으로만 반환해줘.

**문서명**: {filename}
**문서유형**: {doctype}
**날짜**: {display_date}

[문서 내용]
{context_text}

**JSON 스키마**:
{{
  "문서한줄요약": "회의 목적 한 문장",
  "참석자": ["이름1", "이름2", ...],
  "주요안건": ["안건1", "안건2", ...],
  "결정사항": ["결정1", "결정2", ...],
  "액션아이템": [{{"담당자": "이름", "내용": "할 일", "기한": "날짜"}}, ...],
  "주의": "모호한 부분 명시"
}}

**주의사항**:
- 문서에 없는 정보는 null 또는 "없음"
- 800자 이내
- JSON만 반환"""

    # 기본 (일반 문서)
    else:
        user_prompt = f"""아래 문서 내용을 토대로 핵심 정보를 JSON으로만 반환해줘.

**문서명**: {filename}
**문서유형**: {doctype or "일반"}
**날짜**: {display_date}
**금액**: {f"₩{claimed_total:,}" if claimed_total else "null"}

[문서 내용]
{context_text}

**JSON 스키마**:
{{
  "문서한줄요약": "한 문장 요약",
  "목적배경": "이 문서가 작성된 이유",
  "현황": "현재 상황",
  "주요내용": "핵심 내용",
  "결론조치": "최종 결정/조치 사항",
  "예산": {claimed_total if claimed_total else "null"},
  "주의": "모호한 부분 명시"
}}

**주의사항**:
- 문서에 없는 정보는 "없음"
- 중복 금지
- 800자 이내
- JSON만 반환"""

    return system_prompt, user_prompt


def parse_summary_json(response: str) -> Dict[str, Any]:
    """LLM 응답에서 JSON 추출 및 파싱 (강건한 파서)

    Args:
        response: LLM 응답 텍스트

    Returns:
        파싱된 JSON dict, 실패 시 None
    """
    import re

    try:
        # 1단계: ```json ... ``` 블록 제거
        cleaned = re.sub(r"```json|```", "", response).strip()

        # 2단계: 첫 번째 {...} 블록 추출
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None

        json_str = match.group(0)

        # 3단계: JSON 파싱 시도
        try:
            parsed = json.loads(json_str)
            return parsed
        except json.JSONDecodeError:
            # 4단계: 흔한 JSON 오류 수정 시도 (끝 콤마 제거)
            json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
            parsed = json.loads(json_str)
            return parsed

    except Exception as e:
        return None


def format_summary_output(
    parsed_json: Dict[str, Any],
    doctype: str,
    filename: str,
    drafter: str,
    display_date: str,
    claimed_total: int
) -> str:
    """JSON 결과를 마크다운 포맷으로 변환

    Args:
        parsed_json: 파싱된 JSON
        doctype: 문서 유형
        filename: 파일명
        drafter: 기안자
        display_date: 날짜
        claimed_total: 금액

    Returns:
        마크다운 포맷 요약 텍스트
    """
    output = f"**📄 {filename}**\n\n"

    # 기술검토서 (proposal, review)
    if doctype in ["proposal", "review", "기술검토서"]:
        output += f"**📝 {parsed_json.get('문서한줄요약', '요약 없음')}**\n\n"

        # 1. 목적/배경
        output += f"**🎯 목적/배경**\n{parsed_json.get('문제', '없음')}\n\n"

        # 2. 주요 비교/검토
        output += "**🔍 주요 비교/검토**\n"
        products = parsed_json.get('검토제품', [])
        if products and len(products) > 0:
            for i, p in enumerate(products[:3], 1):  # 최대 3개
                model = p.get('모델', '없음')
                spec = p.get('사양', '없음')
                price = p.get('가격', '없음')
                output += f"{i}. {model} - {spec} ({price})\n"
        else:
            output += "없음\n"
        output += "\n"

        # 3. 선정/결정
        output += "**✅ 선정/결정**\n"
        selected = parsed_json.get('선정제품', {})
        if selected and selected.get('모델'):
            output += f"- 선정 제품: {selected.get('모델', '없음')}\n"
            output += f"- 선정 이유: {selected.get('선정이유', '없음')}\n"
        else:
            output += "없음\n"
        output += "\n"

        # 4. 예산
        output += "**💰 예산**\n"
        budget = parsed_json.get('예산') or claimed_total
        if budget:
            output += f"₩{budget:,}\n"
        else:
            output += "없음\n"
        output += "\n"

        # 결론
        if parsed_json.get('결론'):
            output += f"**📌 결론**\n{parsed_json.get('결론')}\n\n"

        # 주의사항
        if parsed_json.get('주의'):
            output += f"⚠️ {parsed_json.get('주의')}\n\n"

    # 회의록
    elif doctype in ["minutes", "회의록"]:
        output += f"**📝 {parsed_json.get('문서한줄요약', '요약 없음')}**\n\n"

        # 참석자
        if parsed_json.get('참석자'):
            output += f"**👥 참석자**: {', '.join(parsed_json['참석자'])}\n\n"

        # 주요 안건
        output += "**📋 주요 안건**\n"
        for i, item in enumerate(parsed_json.get('주요안건', []), 1):
            output += f"{i}. {item}\n"
        output += "\n"

        # 결정사항
        output += "**✅ 결정사항**\n"
        for i, item in enumerate(parsed_json.get('결정사항', []), 1):
            output += f"{i}. {item}\n"
        output += "\n"

        # 액션 아이템
        if parsed_json.get('액션아이템'):
            output += "**🎯 액션 아이템**\n"
            for item in parsed_json['액션아이템']:
                담당자 = item.get('담당자', '없음')
                내용 = item.get('내용', '없음')
                기한 = item.get('기한', '없음')
                output += f"- {담당자}: {내용} (기한: {기한})\n"
            output += "\n"

    # 기본 문서
    else:
        output += f"**📝 {parsed_json.get('문서한줄요약', '요약 없음')}**\n\n"

        output += f"**🎯 목적/배경**\n{parsed_json.get('목적배경', '없음')}\n\n"
        output += f"**📊 현황**\n{parsed_json.get('현황', '없음')}\n\n"
        output += f"**📝 주요 내용**\n{parsed_json.get('주요내용', '없음')}\n\n"
        output += f"**✅ 결론/조치**\n{parsed_json.get('결론조치', '없음')}\n\n"

        budget = parsed_json.get('예산') or claimed_total
        if budget:
            output += f"**💰 예산**: ₩{budget:,}\n\n"

    # 하단 메타데이터
    output += "---\n**📋 문서 정보**\n"
    output += f"- 기안자: {drafter or '정보 없음'}\n"
    output += f"- 날짜: {display_date or '정보 없음'}\n"

    return output
