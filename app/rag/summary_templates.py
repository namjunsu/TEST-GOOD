"""
문서 유형별 요약 프롬프트 템플릿 (v2)
2025-10-27

목적: 문서 타입 자동 감지 + 맞춤 프롬프트로 요약 품질 급상승
핵심: "틀 채우기" 제거, "진짜 읽고 정리" 구현
"""

from typing import Dict, Any, Optional, Tuple
import json
import re


def detect_doc_kind(filename: str, text: str) -> str:
    """파일명 + 본문으로 문서 종류 자동 감지

    Args:
        filename: 파일명
        text: 문서 본문 (앞부분 2000자 정도)

    Returns:
        문서 종류: repair/proc_eval/disposal/minutes/generic
    """
    s = f"{filename}\n{text[:2000]}".lower()

    # 수리/장애 문서
    if re.search(r"(수리|수리건|수리\s*내역|불량|고장|장애|as\b|a/s)", s):
        return "repair"

    # 구매/교체 검토서
    if re.search(r"(교체|교체\s*검토서|도입|구매|검토서|검토의\s*건|견적|비교)", s):
        return "proc_eval"

    # 폐기 문서
    if re.search(r"(폐기|불용|scrap|disposal|폐기의\s*건)", s):
        return "disposal"

    # 회의록
    if re.search(r"(회의록|회의\s*결과|안건|참석자|결정\s*사항)", s):
        return "minutes"

    return "generic"


def _recheck_money_and_decision(text: str, claimed_total: Optional[int]) -> Tuple[Optional[int], bool]:
    """본문 재스캔으로 "없음" 남발 방지

    Args:
        text: 문서 본문
        claimed_total: 파이프라인에서 추출한 금액

    Returns:
        (재확인된 금액, 결정사항 존재 여부)
    """
    # 금액 재확인 (claimed_total이 None일 때만)
    money = claimed_total
    if not money:
        # 합계|총액|비용 패턴 스캔
        money_match = re.search(r"(합계|총액|비용|견적|금액)\s*[:\s]\s*([\d,]+)\s*원?", text)
        if money_match:
            try:
                money_str = money_match.group(2).replace(",", "")
                money = int(money_str)
            except:
                pass

    # 결정/선정 사항 존재 여부
    decision_present = bool(re.search(r"(선정|결정|조치|확정|권고|채택|승인)", text))

    return money, decision_present


def build_prompt(
    kind: str,
    filename: str,
    drafter: str,
    display_date: str,
    context_text: str,
    claimed_total: Optional[int]
) -> str:
    """문서 종류별 맞춤 프롬프트 생성

    Args:
        kind: 문서 종류 (repair/proc_eval/disposal/minutes/generic)
        filename: 파일명
        drafter: 기안자
        display_date: 날짜
        context_text: 문서 본문 (RAG + PDF 끝 + 스냅샷)
        claimed_total: 추출된 금액

    Returns:
        LLM 프롬프트 (system + user 통합)
    """
    # 금액/결정 재확인
    money, has_decision = _recheck_money_and_decision(context_text, claimed_total)
    money_str = f"₩{money:,}" if money else "없음"

    # 공통 헤더
    common_header = f"""너는 회사 내부 문서를 **추측 없이** 정확히 요약하는 보조자다.
반드시 문서에 있는 정보만 쓰고, 각 항목은 1~2문장으로 간결하게.
없으면 '없음'이라고 쓰되, 본문을 꼼꼼히 읽은 후 정말 없을 때만 '없음'을 쓰세요.
JSON만 반환하세요.

**문서명**: {filename}
**기안자**: {drafter or '정보 없음'}
**날짜**: {display_date or '정보 없음'}
**추출 금액**: {money_str}

[원문]
{context_text}
"""

    # 수리/장애 문서
    if kind == "repair":
        return common_header + """
**출력 JSON 스키마**:
{
  "제목": "문서 제목 (한 문장)",
  "요약": "수리 내용 핵심 1문장",
  "증상": ["발생한 문제/고장 증상"],
  "원인": ["원인 분석 결과. 없으면 '없음'"],
  "조치": ["수리 방법, 교체 부품, 수리 업체"],
  "결과검증": ["정상 확인 여부, 테스트 결과"],
  "비용": "숫자 또는 '없음'",
  "증거": [{"page": 페이지번호, "quote": "원문 인용 20자"}]
}

**주의사항**:
- "수리건"이면 반드시 어디서/어떻게 수리했는지 찾을 것
- "정상 확인" 여부는 필수. 없으면 명시
- 비용이 정말 없으면 '없음', 아니면 숫자로
- JSON만 반환 (다른 설명 금지)
"""

    # 구매/교체 검토서
    elif kind == "proc_eval":
        decision_hint = "본문에서 선정/결정 키워드 확인됨. 반드시 찾을 것." if has_decision else "선정 내용이 없으면 '없음'"
        return common_header + f"""
**출력 JSON 스키마**:
{{
  "제목": "문서 제목 (한 문장)",
  "요약": "검토 핵심 1문장",
  "배경목적": "왜 이 검토를 하는가",
  "비교대안": [
    {{"모델": "제품명/모델명", "사양특징": "핵심 스펙", "가격": "가격 정보 또는 '없음'"}},
    ...
  ],
  "선정권고": "최종 선정 제품과 이유. {decision_hint}",
  "예산합계": "{money_str}",
  "증거": [{{"page": n, "quote": "..."}}]
}}

**주의사항**:
- 비교대안은 최대 3개만 (핵심만)
- 선정 제품이 정말 없으면 '없음', 있으면 반드시 기재
- 금액은 본문에서 재확인 (합계/총액/견적)
- JSON만 반환
"""

    # 폐기 문서
    elif kind == "disposal":
        return common_header + """
**출력 JSON 스키마**:
{
  "제목": "문서 제목 (한 문장)",
  "요약": "폐기 핵심 1문장",
  "폐기사유": "왜 폐기하는가",
  "폐기대상": [{"품명": "...", "수량": "...", "취득일/사용기간": "..."}],
  "폐기방법": "폐기 절차/방법",
  "증거": [{"page": n, "quote": "..."}]
}

**주의사항**:
- 폐기 사유는 필수 (노후화/고장/교체 등)
- 취득일이나 사용 기간 있으면 기재
- JSON만 반환
"""

    # 회의록
    elif kind == "minutes":
        return common_header + """
**출력 JSON 스키마**:
{
  "제목": "회의 제목 (한 문장)",
  "요약": "회의 목적 1문장",
  "참석자": ["이름1", "이름2", ...],
  "주요안건": ["안건1", "안건2", ...],
  "결정사항": ["결정1", "결정2", ...],
  "액션아이템": [{"담당자": "...", "내용": "...", "기한": "..."}],
  "증거": [{"page": n, "quote": "..."}]
}

**주의사항**:
- 참석자는 이름만 (직함 제외)
- 결정사항과 액션아이템 구분
- JSON만 반환
"""

    # 일반 문서
    else:
        return common_header + f"""
**출력 JSON 스키마**:
{{
  "제목": "문서 제목 (한 문장)",
  "요약": "문서 핵심 1문장",
  "목적배경": "이 문서가 작성된 이유",
  "주요내용": "핵심 내용 2~3문장",
  "결론조치": "최종 결정/조치 사항",
  "예산": "{money_str}",
  "증거": [{{"page": n, "quote": "..."}}]
}}

**주의사항**:
- 결론/조치는 문서 말미에 주로 있음. 꼼꼼히 확인
- 예산이 없으면 '없음'
- JSON만 반환
"""


def parse_summary_json(response: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 추출 및 파싱 (강건한 파서)

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

    except Exception:
        return None


def format_summary_output(
    parsed_json: Dict[str, Any],
    kind: str,
    filename: str,
    drafter: str,
    display_date: str,
    claimed_total: Optional[int]
) -> str:
    """JSON 결과를 마크다운으로 동적 렌더링 (존재하는 섹션만 표시)

    Args:
        parsed_json: 파싱된 JSON
        kind: 문서 종류
        filename: 파일명
        drafter: 기안자
        display_date: 날짜
        claimed_total: 금액

    Returns:
        마크다운 포맷 요약 텍스트
    """
    if not parsed_json:
        return "⚠️ 요약 생성 중 오류가 발생했습니다.\n\n문서를 직접 확인하시려면 미리보기를 이용해주세요."

    output = f"**📄 {parsed_json.get('제목') or filename}**\n\n"

    # 요약 (공통)
    if parsed_json.get('요약'):
        output += f"**📝 {parsed_json['요약']}**\n\n"

    # 수리 문서
    if kind == "repair":
        if parsed_json.get('증상'):
            output += "**🔧 증상**\n"
            for item in parsed_json['증상']:
                output += f"- {item}\n"
            output += "\n"

        if parsed_json.get('원인'):
            output += "**🔍 원인**\n"
            for item in parsed_json['원인']:
                output += f"- {item}\n"
            output += "\n"

        if parsed_json.get('조치'):
            output += "**✅ 조치**\n"
            for item in parsed_json['조치']:
                output += f"- {item}\n"
            output += "\n"

        if parsed_json.get('결과검증'):
            output += "**✓ 결과/검증**\n"
            for item in parsed_json['결과검증']:
                output += f"- {item}\n"
            output += "\n"

        if parsed_json.get('비용') and parsed_json['비용'] != '없음':
            output += f"**💰 비용**: {parsed_json['비용']}\n\n"

    # 구매/교체 검토서
    elif kind == "proc_eval":
        if parsed_json.get('배경목적'):
            output += f"**🎯 배경/목적**\n{parsed_json['배경목적']}\n\n"

        if parsed_json.get('비교대안') and len(parsed_json['비교대안']) > 0:
            output += "**🔍 비교 대안**\n"
            for i, item in enumerate(parsed_json['비교대안'][:3], 1):
                model = item.get('모델', '없음')
                spec = item.get('사양특징', '없음')
                price = item.get('가격', '없음')
                output += f"{i}. **{model}** - {spec} ({price})\n"
            output += "\n"

        if parsed_json.get('선정권고') and parsed_json['선정권고'] != '없음':
            output += f"**✅ 선정/권고**\n{parsed_json['선정권고']}\n\n"

        budget = parsed_json.get('예산합계') or claimed_total
        if budget and str(budget) != '없음':
            if isinstance(budget, int):
                output += f"**💰 예산/합계**: ₩{budget:,}\n\n"
            else:
                output += f"**💰 예산/합계**: {budget}\n\n"

    # 폐기 문서
    elif kind == "disposal":
        if parsed_json.get('폐기사유'):
            output += f"**🎯 폐기 사유**\n{parsed_json['폐기사유']}\n\n"

        if parsed_json.get('폐기대상'):
            output += "**📦 폐기 대상**\n"
            for item in parsed_json['폐기대상']:
                품명 = item.get('품명', '없음')
                수량 = item.get('수량', '없음')
                취득 = item.get('취득일/사용기간', '없음')
                output += f"- {품명} (수량: {수량}, 취득/사용: {취득})\n"
            output += "\n"

        if parsed_json.get('폐기방법'):
            output += f"**♻️ 폐기 방법**\n{parsed_json['폐기방법']}\n\n"

    # 회의록
    elif kind == "minutes":
        if parsed_json.get('참석자'):
            output += f"**👥 참석자**: {', '.join(parsed_json['참석자'])}\n\n"

        if parsed_json.get('주요안건'):
            output += "**📋 주요 안건**\n"
            for i, item in enumerate(parsed_json['주요안건'], 1):
                output += f"{i}. {item}\n"
            output += "\n"

        if parsed_json.get('결정사항'):
            output += "**✅ 결정 사항**\n"
            for i, item in enumerate(parsed_json['결정사항'], 1):
                output += f"{i}. {item}\n"
            output += "\n"

        if parsed_json.get('액션아이템'):
            output += "**🎯 액션 아이템**\n"
            for item in parsed_json['액션아이템']:
                담당 = item.get('담당자', '없음')
                내용 = item.get('내용', '없음')
                기한 = item.get('기한', '없음')
                output += f"- {담당}: {내용} (기한: {기한})\n"
            output += "\n"

    # 일반 문서
    else:
        if parsed_json.get('목적배경'):
            output += f"**🎯 목적/배경**\n{parsed_json['목적배경']}\n\n"

        if parsed_json.get('주요내용'):
            output += f"**📝 주요 내용**\n{parsed_json['주요내용']}\n\n"

        if parsed_json.get('결론조치'):
            output += f"**✅ 결론/조치**\n{parsed_json['결론조치']}\n\n"

        budget = parsed_json.get('예산') or claimed_total
        if budget and str(budget) != '없음':
            if isinstance(budget, int):
                output += f"**💰 예산**: ₩{budget:,}\n\n"
            else:
                output += f"**💰 예산**: {budget}\n\n"

    # 증거 (있으면)
    if parsed_json.get('증거') and len(parsed_json['증거']) > 0:
        output += "**📌 근거**\n"
        for ev in parsed_json['증거'][:2]:  # 최대 2개
            page = ev.get('page', '?')
            quote = ev.get('quote', '없음')
            output += f"- p.{page}: \"{quote}\"\n"
        output += "\n"

    # 하단 메타데이터
    output += "---\n**📋 문서 정보**\n"
    output += f"- 기안자: {drafter or '정보 없음'}\n"
    output += f"- 날짜: {display_date or '정보 없음'}\n"

    return output
