# app/utils/text_normalizer.py
import re
from typing import List, Optional

DETAIL_KEYWORDS = [
    "자세히", "상세히", "자세하게", "상세하게", "구체적으로", "디테일",
    "세부사항", "풀버전", "풀로", "전부", "모두", "전체",
    "detail", "full", "full ver", "full version"
]

def normalize_query(q: str) -> str:
    """쿼리 정규화: 공백/어미/강조 변형 흡수

    Args:
        q: 원본 쿼리

    Returns:
        정규화된 쿼리
    """
    s = (q or "").strip()
    # 소문자화(한글 영향 없음), 다중 공백 정리
    s = s.lower()
    s = re.sub(r"\s+", " ", s)

    # 한국어 어미/강조 변형 흡수: "자세히좀/자세히요/자세하게요" 등
    s = re.sub(r"(자세히|상세히)(요|좀|하게|하게요|하게좀)?", r"\1", s)
    s = re.sub(r"(자세하게|상세하게)(요|좀)?", lambda m: m.group(0).replace("하게", "히"), s)

    # 영문 변형 통일
    s = s.replace("full ver", "full ver")
    s = s.replace("full version", "full version")

    # 특수문자 과다 제거(표/단가 등 정규 수치 표현은 손대지 않음)
    s = re.sub(r"[''""]", "\"", s)
    return s


def is_detailed_mode(q: str, extra_keywords: Optional[List[str]] = None) -> bool:
    """상세 답변 모드 감지

    Args:
        q: 원본 쿼리
        extra_keywords: 추가 키워드 (프로젝트별 확장용)

    Returns:
        상세 모드 여부
    """
    nq = normalize_query(q)
    kws = set(DETAIL_KEYWORDS + (extra_keywords or []))
    return any(kw.lower() in nq for kw in kws)


SECTION_PATTERNS = {
    "배경/목적": r"(배경|목적)",
    "현황": r"(현황|현 상태|상태|운영 현황|장비 현황)",
    "검토 내용": r"(검토 ?내용|세부 ?검토|검토사항|기술 ?검토)",
    "비교 대안": r"(비교 ?대안|대안 ?비교|대안|옵션)",
    "선정 사유": r"(선정 ?사유|채택 ?사유|採用 ?사유|선정 ?기준)",
    "예산/비용": r"(예산|비용|금액|단가|총액|견적|원가)",
    "리스크": r"(리스크|위험|한계|제약|이슈)",
    "일정/계획": r"(일정|타임라인|계획|로드맵)"
}


def detect_section(q: str) -> Optional[str]:
    """섹션 앵커 감지

    Args:
        q: 원본 쿼리

    Returns:
        감지된 섹션명 또는 None
    """
    nq = normalize_query(q)
    for sec, pat in SECTION_PATTERNS.items():
        if re.search(pat, nq):
            return sec
    return None
