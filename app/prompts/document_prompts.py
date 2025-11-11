# app/prompts/document_prompts.py
"""문서 질의 프롬프트 템플릿 모음

템플릿 변수:
- {context}: 검색된 문서 패시지
- {section}: 섹션명 (SECTION_PROMPT 전용)
- {filename}: 파일명
- {drafter}: 기안자
- {date}: 날짜
"""

DETAILED_PROMPT = """다음 지침에 따라 완전한 상세 답변을 작성하라.

[지침]
1) 문서의 모든 섹션(배경/목적, 현황, 검토 내용, 비교 대안, 선정 사유, 예산/비용 등)을 빠짐없이 기술한다.
2) 금액·날짜·담당자·모델명·사양(규격)·수량·단가·합계를 원문 그대로 정확히 인용한다.
3) 표/목록은 가능한 동일 구조로 재현한다. 표 헤더와 단위를 유지한다.
4) 비교 대안은 전부 열거하고, 각 장단점/비용/리스크를 구분 표기한다.
5) 누락된 섹션이 있을 경우, "누락 섹션" 목록을 끝에 명시한다.

[출력 형식]
- 섹션별 제목을 명확히 구분
- 표는 마크다운 표로 재현
- 숫자에는 단위를 기입 (예: KRW, 개, 대, Gbps, inch)

[근거 패시지]
{context}
"""

SECTION_PROMPT = """다음 문서에서 "{section}" 섹션만 정확히 발췌·정리하라.
- 금액/날짜/사양/표 구조를 유지하라.
- 범위를 벗어난 서술 금지.

[근거 패시지]
{context}
"""

SUMMARY_PROMPT = """다음 문서의 핵심을 10~12문장으로 요약하라.
- 핵심 수치(금액/날짜/사양)만 포함
- 표는 3~5행으로 축약

[근거 패시지]
{context}
"""

QA_PROMPT = """사용자 질문에 정확히 답하라. 문서 근거에 한정한다.

[근거 패시지]
{context}
"""


def build_detailed_prompt(context: str, filename: str = "", drafter: str = "", date: str = "") -> str:
    """상세 답변 프롬프트 생성

    Args:
        context: 문서 내용
        filename: 파일명
        drafter: 기안자
        date: 날짜

    Returns:
        완성된 프롬프트
    """
    header = ""
    if filename or drafter or date:
        header = "문서 정보:\n"
        if filename:
            header += f"- 파일명: {filename}\n"
        if drafter:
            header += f"- 기안자: {drafter}\n"
        if date:
            header += f"- 날짜: {date}\n"
        header += "\n"

    return header + DETAILED_PROMPT.format(context=context)


def build_section_prompt(context: str, section: str, filename: str = "", drafter: str = "", date: str = "") -> str:
    """섹션별 프롬프트 생성

    Args:
        context: 문서 내용
        section: 섹션명
        filename: 파일명
        drafter: 기안자
        date: 날짜

    Returns:
        완성된 프롬프트
    """
    header = ""
    if filename or drafter or date:
        header = "문서 정보:\n"
        if filename:
            header += f"- 파일명: {filename}\n"
        if drafter:
            header += f"- 기안자: {drafter}\n"
        if date:
            header += f"- 날짜: {date}\n"
        header += "\n"

    return header + SECTION_PROMPT.format(context=context, section=section)


def build_summary_prompt(context: str, filename: str = "", drafter: str = "", date: str = "") -> str:
    """요약 프롬프트 생성

    Args:
        context: 문서 내용
        filename: 파일명
        drafter: 기안자
        date: 날짜

    Returns:
        완성된 프롬프트
    """
    header = ""
    if filename or drafter or date:
        header = "문서 정보:\n"
        if filename:
            header += f"- 파일명: {filename}\n"
        if drafter:
            header += f"- 기안자: {drafter}\n"
        if date:
            header += f"- 날짜: {date}\n"
        header += "\n"

    return header + SUMMARY_PROMPT.format(context=context)


def build_qa_prompt(context: str, query: str, filename: str = "", drafter: str = "", date: str = "") -> str:
    """Q&A 프롬프트 생성

    Args:
        context: 문서 내용
        query: 사용자 질문
        filename: 파일명
        drafter: 기안자
        date: 날짜

    Returns:
        완성된 프롬프트
    """
    header = ""
    if filename or drafter or date:
        header = "문서 정보:\n"
        if filename:
            header += f"- 파일명: {filename}\n"
        if drafter:
            header += f"- 기안자: {drafter}\n"
        if date:
            header += f"- 날짜: {date}\n"
        header += "\n"

    return header + f"사용자 질문: {query}\n\n" + QA_PROMPT.format(context=context)
