"""
문서 유형별 요약 프롬프트 템플릿 (v3)
2025-11-10

목적: 문서 타입 자동 감지 + 맞춤 프롬프트로 요약 품질 급상승
핵심: "틀 채우기" 제거, "진짜 읽고 정리" 구현
개선: 회의록 우선 분류, 금액 파싱 강화, JSON 추출 안정화
"""

import json
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

# Compiled regex patterns for performance
_KW = {
    "minutes": re.compile(
        r"(회의록|회의\s*결과|회의\s*일시|회의\s*장소|참석자|안건|결정\s*사항)",
        re.IGNORECASE
    ),
    "proc_eval": re.compile(
        r"(기술\s*검토서|구매\s*검토서|검토의\s*건|견적\s*비교|도입\s*검토|교체\s*검토|선정|권고|proposal)",
        re.IGNORECASE
    ),
    "consumables": re.compile(
        r"(소모품|consumable|구매\s*의\s*건|납품|발주)",
        re.IGNORECASE
    ),
    "repair": re.compile(
        r"(수리(?:\s*내역)?|불량|고장|장애|\bAS\b|A/S)",
        re.IGNORECASE
    ),
    "disposal": re.compile(
        r"(폐기|불용|SCRAP|disposal|폐기의\s*건)",
        re.IGNORECASE
    ),
}

# Money parsing patterns
_MONEY_NUM = re.compile(r"([\d]{1,3}(?:[,]\d{3})+|\d+)\s*원?")
_MONEY_UNIT = re.compile(r"(?:(\d+(?:\.\d+)?)\s*억)|(?:(\d+(?:\.\d+)?)\s*만)")
_VAT_FLAG = re.compile(r"(부가세|VAT)\s*(별도|포함)", re.IGNORECASE)


def _norm(s: str) -> str:
    """Normalize text: NFKC + whitespace standardization"""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return s


def detect_doc_kind(filename: str, text: str) -> str:
    """파일명 + 본문으로 문서 종류 자동 감지 (v2: 회의록 우선)

    Args:
        filename: 파일명
        text: 문서 본문 (앞부분 2000자 정도)

    Returns:
        문서 종류: consumables/repair/proc_eval/disposal/minutes/generic
    """
    s = _norm(f"{filename}\n{text[:2000]}").lower()

    # 회의록 강한 시그널 우선 (오분류 방지)
    # '안건/참석자/결정' 중 2개 이상 동시 존재 시 minutes 확정
    if _KW["minutes"].search(s):
        score = sum(1 for k in ["안건", "참석자", "결정"] if k in s)
        if score >= 2:
            return "minutes"

    # 구매/교체 검토서
    if _KW["proc_eval"].search(s):
        return "proc_eval"

    # 소모품/구매 문서 (검토서 이후 검사)
    if _KW["consumables"].search(s):
        return "consumables"

    # 수리/장애 문서
    if _KW["repair"].search(s):
        return "repair"

    # 폐기 문서
    if _KW["disposal"].search(s):
        return "disposal"

    return "generic"


def parse_money_any(s: str) -> Optional[int]:
    """금액 파싱: 억/만 단위, 콤마 표기, VAT 고려

    Args:
        s: 입력 문자열

    Returns:
        파싱된 금액 (KRW 정수), 실패 시 None
    """
    s = _norm(s)

    # 1) 억/만 단위
    u = _MONEY_UNIT.search(s)
    if u:
        eok = u.group(1)
        man = u.group(2)
        if eok:
            return int(round(float(eok) * 100_000_000))
        if man:
            return int(round(float(man) * 10_000))

    # 2) 쉼표/원 표기
    n = _MONEY_NUM.search(s)
    if n:
        return int(n.group(1).replace(",", ""))

    return None


def _windowed_money_candidates(text: str, window: int = 60) -> list:
    """금액 주변 윈도우에서 후보 추출

    Args:
        text: 문서 본문
        window: 키워드 주변 검색 범위

    Returns:
        금액 후보 리스트
    """
    cand = []

    # '합계/총액/견적/금액' 주변 윈도우 우선 스캔
    for m in re.finditer(r"(합계|총액|견적|금액).{0,%d}" % window, text, re.IGNORECASE | re.DOTALL):
        seg = text[m.start(): m.end() + window]
        val = parse_money_any(seg)
        if val:
            cand.append(val)

    # 일반 숫자 표기도 보조로 스캔
    for m in _MONEY_NUM.finditer(text):
        try:
            cand.append(int(m.group(1).replace(",", "")))
        except Exception:
            pass

    return cand


def _recheck_money_and_decision(text: str, claimed_total: Optional[int]) -> Tuple[Optional[int], bool]:
    """본문 재스캔으로 "없음" 남발 방지 (v2: 억/만 지원)

    Args:
        text: 문서 본문
        claimed_total: 파이프라인에서 추출한 금액

    Returns:
        (재확인된 금액, 결정사항 존재 여부)
    """
    money = claimed_total
    if not money:
        cands = _windowed_money_candidates(text, window=80)
        money = max(cands) if cands else None

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
반드시 문서에 있는 정보만 쓰되, 상세하고 완전하게 작성하세요.
없으면 '없음'이라고 쓰되, 본문을 꼼꼼히 읽은 후 정말 없을 때만 '없음'을 쓰세요.

**중요 출력 형식**:
- 반드시 ```json ... ``` fenced code 블록 안에 JSON을 작성하세요.
- JSON 외 다른 설명이나 주석은 절대 포함하지 마세요.
- 순수 JSON 객체만 출력하세요.

**문서명**: {filename}
**기안자**: {drafter or '정보 없음'}
**날짜**: {display_date or '정보 없음'}
**추출 금액**: {money_str}

[원문]
{context_text}
"""

    # 소모품/구매 문서
    if kind == "consumables":
        return common_header + f"""
**출력 JSON 스키마**:
{{
  "제목": "문서 제목 (한 문장)",
  "요약": "구매 핵심 1문장",
  "구매목적": "왜 이 소모품을 구매하는가",
  "품목": [
    {{"품명": "제품명", "규격모델": "규격/모델 정보", "수량": "수량 정보", "단가": "단가 또는 '없음'", "금액": "품목별 금액 또는 '없음'"}}
  ],
  "총액": "{money_str}",
  "예산계정": "예산 출처/계정과목 (있으면)",
  "납품장소": "납품 위치 (있으면)",
  "비고": "특이사항 (있으면)",
  "증거": [{{"page": n, "quote": "..."}}]
}}

**주의사항**:
- 품목 배열은 본문에서 찾은 모든 항목 포함
- 단가/금액이 없으면 '없음'으로 명시
- 총액은 반드시 확인 (합계/총액/견적 키워드)
- 납품장소는 본문에서 "납품처", "배송지", "설치 장소" 등을 찾을 것
- JSON만 반환
"""

    # 수리/장애 문서
    elif kind == "repair":
        return common_header + """
**출력 JSON 스키마**:
{
  "제목": "문서 제목 (한 문장)",
  "요약": "수리 내용 핵심 1~2문장 (장비명, 문제, 조치 포함)",
  "장비정보": {
    "장비명": "수리 대상 장비명 (구체적으로)",
    "장비설명": "장비의 기능이나 역할 설명 (있으면)",
    "장비현황": "보유 현황/수량 정보 (있으면)"
  },
  "증상": ["발생한 문제/고장 증상 (구체적으로, 여러 개 가능)"],
  "원인": ["원인 분석 결과 (정확한 부품명 포함). 없으면 '없음'"],
  "조치": ["수리 방법, 교체 부품명, 수리 업체명 (구체적으로)"],
  "결과검증": ["정상 확인 여부, 테스트 결과, 사용 재개 여부"],
  "비용상세": {
    "업체명": "수리 업체명",
    "품명": "수리 내용/교체 부품",
    "단가": "단가 정보",
    "총액": "총 비용 (숫자)"
  },
  "긴급도": "생방송 장비, 긴급 수리 등의 정보 (있으면)",
  "증거": [{"page": 페이지번호, "quote": "원문 인용 20자"}]
}

**주의사항**:
- 장비명과 기능을 구체적으로 작성 (예: "지미집 Control Box - 카메라 원격 제어 장치")
- 증상은 발생한 문제를 명확히 기술 (예: "Tilt 스피드 조절 장애")
- 원인은 정확한 부품명 포함 (예: "Tilt 스피드단 고장")
- 조치는 수리 업체와 교체 부품 명시 (예: "㈜삼아 GVC, Tilt 스피드단 부품 교체")
- 비용은 업체명, 품명, 금액 모두 포함
- 생방송 장비 등 긴급도가 언급되면 반드시 포함
- JSON만 반환 (다른 설명 금지)
"""

    # 구매/교체 검토서
    elif kind == "proc_eval":
        decision_hint = "본문에서 선정/결정 키워드 확인됨. 반드시 찾을 것." if has_decision else "선정 내용이 없으면 '없음'"
        return common_header + f"""
**출력 JSON 스키마**:
{{
  "제목": "문서 제목",
  "예산합계": "{money_str}",
  "배경목적": "검토 배경 (1-2문장)",
  "비교대안": [
    {{"모델": "제품명", "사양": "스펙 요약", "수량": "수량", "가격": "가격"}},
    ...
  ],
  "선정권고": "최종 선정 제품. {decision_hint}"
}}

**주의사항**:
- 비교대안은 최대 4개까지만
- 모델명, 수량, 가격은 필수
- 예산합계는 반드시 맨 위에 기재
- JSON만 반환, 다른 텍스트 금지
- 반드시 }} 로 닫기
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


def _extract_first_json_object(s: str) -> Optional[str]:
    """스택 기반 중괄호 밸런싱으로 첫 완결 JSON 객체 추출

    Args:
        s: 입력 문자열

    Returns:
        첫 JSON 객체 문자열, 실패 시 None
    """
    # Fenced code block 우선
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)

    # 스택 기반 탐색
    start = None
    depth = 0
    for i, ch in enumerate(s):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return s[start:i + 1]
    return None


def parse_summary_json(response: str) -> Optional[Dict[str, Any]]:
    """LLM 응답에서 JSON 추출 및 파싱 (v2: 스택 기반)

    Args:
        response: LLM 응답 텍스트

    Returns:
        파싱된 JSON dict, 실패 시 None
    """
    try:
        block = _extract_first_json_object(response)
        if not block:
            return None

        try:
            return json.loads(block)
        except json.JSONDecodeError:
            # 미세 보정: 끝 콤마 제거
            block = re.sub(r",\s*([}\]])", r"\1", block)
            return json.loads(block)

    except Exception:
        return None


def _to_int_or_none(v: Any) -> Optional[int]:
    """금액을 정수로 정규화

    Args:
        v: 입력 값 (int, str, None)

    Returns:
        정수 KRW, 변환 실패 시 None
    """
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v == "없음":
            return None
        try:
            return int(v.replace(",", "").replace("₩", ""))
        except Exception:
            # 억/만 단위 시도
            pm = parse_money_any(v)
            return pm
    return None


def _fmt_krw(v: Optional[int]) -> str:
    """금액 포맷팅

    Args:
        v: 금액 (정수)

    Returns:
        포맷팅된 문자열
    """
    return f"₩{v:,}" if isinstance(v, int) else "없음"


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

    output = f"📄 {parsed_json.get('제목') or filename}\n\n"

    # 요약 (공통)
    if parsed_json.get('요약'):
        output += f"📝 요약\n{parsed_json['요약']}\n\n"

    # 소모품/구매 문서
    if kind == "consumables":
        if parsed_json.get('구매목적'):
            output += f"**🎯 구매 목적**\n{parsed_json['구매목적']}\n\n"

        if parsed_json.get('품목') and len(parsed_json['품목']) > 0:
            output += "**📦 품목 내역**\n"
            for i, item in enumerate(parsed_json['품목'], 1):
                품명 = item.get('품명', '없음')
                규격 = item.get('규격모델', '없음')
                수량 = item.get('수량', '없음')
                단가 = item.get('단가', '없음')
                금액 = item.get('금액', '없음')
                output += f"{i}. **{품명}** - {규격}\n"
                output += f"   - 수량: {수량}"
                if 단가 != '없음':
                    output += f" | 단가: {단가}"
                if 금액 != '없음':
                    output += f" | 금액: {금액}"
                output += "\n"
            output += "\n"

        총액 = parsed_json.get('총액')
        if 총액 and str(총액) != '없음':
            output += f"**💰 총액**: {총액}\n\n"

        if parsed_json.get('예산계정') and parsed_json['예산계정'] != '없음':
            output += f"**📊 예산/계정**: {parsed_json['예산계정']}\n\n"

        if parsed_json.get('납품장소') and parsed_json['납품장소'] != '없음':
            output += f"**📍 납품 장소**: {parsed_json['납품장소']}\n\n"

        if parsed_json.get('비고') and parsed_json['비고'] != '없음':
            output += f"**📌 비고**: {parsed_json['비고']}\n\n"

    # 수리 문서
    elif kind == "repair":
        # 장비 정보
        if parsed_json.get('장비정보'):
            equip_info = parsed_json['장비정보']
            if equip_info.get('장비명'):
                output += f"**🔧 장비명**: {equip_info['장비명']}\n"
            if equip_info.get('장비설명'):
                output += f"**📝 장비 설명**: {equip_info['장비설명']}\n"
            if equip_info.get('장비현황'):
                output += f"**📊 장비 현황**: {equip_info['장비현황']}\n"
            output += "\n"

        # 증상
        if parsed_json.get('증상'):
            output += "**⚠️ 증상**\n"
            for item in parsed_json['증상']:
                output += f"- {item}\n"
            output += "\n"

        # 원인
        if parsed_json.get('원인'):
            output += "**🔍 원인**\n"
            for item in parsed_json['원인']:
                output += f"- {item}\n"
            output += "\n"

        # 조치
        if parsed_json.get('조치'):
            output += "**✅ 조치**\n"
            for item in parsed_json['조치']:
                output += f"- {item}\n"
            output += "\n"

        # 결과/검증
        if parsed_json.get('결과검증'):
            output += "**✓ 결과/검증**\n"
            for item in parsed_json['결과검증']:
                output += f"- {item}\n"
            output += "\n"

        # 비용 상세
        if parsed_json.get('비용상세'):
            cost_detail = parsed_json['비용상세']
            output += "**💰 비용 상세**\n"
            if cost_detail.get('업체명'):
                output += f"- 업체: {cost_detail['업체명']}\n"
            if cost_detail.get('품명'):
                output += f"- 품명: {cost_detail['품명']}\n"
            if cost_detail.get('단가'):
                output += f"- 단가: {cost_detail['단가']}\n"
            if cost_detail.get('총액'):
                total = cost_detail['총액']
                if isinstance(total, int):
                    output += f"- **총액: ₩{total:,}**\n"
                else:
                    output += f"- **총액: {total}**\n"
            output += "\n"

        # 긴급도
        if parsed_json.get('긴급도') and parsed_json['긴급도'] != '없음':
            output += f"**⏰ 긴급도**: {parsed_json['긴급도']}\n\n"

    # 구매/교체 검토서
    elif kind == "proc_eval":
        if parsed_json.get('배경목적'):
            output += f"🎯 배경/목적\n{parsed_json['배경목적']}\n\n"

        if parsed_json.get('비교대안') and len(parsed_json['비교대안']) > 0:
            output += "🔍 비교 대안\n\n"
            for i, item in enumerate(parsed_json['비교대안'][:4], 1):  # 최대 4개까지 표시
                model = item.get('모델', '없음')
                spec = item.get('사양', '없음')  # 수정: '사양특징' → '사양'
                qty = item.get('수량', '')
                price = item.get('가격', '없음')
                # 수량 정보가 있으면 추가
                qty_str = f" x{qty}" if qty and qty != '없음' else ""
                output += f"{i}. {model}{qty_str}\n   - 사양: {spec}\n   - 가격: {price}\n\n"

        if parsed_json.get('선정권고') and parsed_json['선정권고'] != '없음':
            output += f"✅ 선정/권고\n{parsed_json['선정권고']}\n\n"

        budget = parsed_json.get('예산합계') or claimed_total
        if budget and str(budget) != '없음':
            if isinstance(budget, int):
                output += f"💰 예산/합계: ₩{budget:,}\n\n"
            else:
                output += f"💰 예산/합계: {budget}\n\n"

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
