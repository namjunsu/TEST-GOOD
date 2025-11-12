#!/usr/bin/env python3
"""
텍스트 정규화 유틸리티 v2.0
쿼리 정규화, 상세모드 감지, 섹션 앵커 감지

개선사항:
1. 정규식 문법 오류 수정 (따옴표 클래스)
2. 고위험 키워드 과검출 방지 (문맥 패턴)
3. 영문/한글 표기 변형 표준화 (full version, 풀버전)
4. 섹션 충돌 해결 (우선순위 기반)
5. 영문 키워드 보강 (국제 문서 대응)
6. 한국어 변형 처리 간소화
"""
import re
from typing import List, Optional

# 상세모드 트리거(저위험 키워드 우선, 고위험 단어는 문맥 제약으로 처리)
DETAIL_KEYWORDS_BASE = [
    "자세히",
    "상세히",
    "구체적으로",
    "디테일",
    "세부사항",
    "풀버전",
    "풀 버전",
    "detail",
    "full ver",
    "full version",
]

# 고위험(일반 검색에도 흔함): 단독 사용 시 과검출 → 문맥 패턴으로만 허용
DETAIL_HIGH_RISK = ["전부", "모두", "전체", "풀로"]

# 영문/한글 변형 표준화 매핑
_CANON_MAP = {
    r"\bfull[-\s]?ver(sion)?\b": "full version",
    r"\bfullversion\b": "full version",
    r"\bfullver\b": "full version",
    r"\bfull\-?ver\b": "full version",
}

# 한글 표기 변형
_KO_CANON_MAP = {
    r"풀[\s\-]?버(전|젼)": "풀버전",
}

# 유니코드 따옴표/아포스트로피 정규화
_QUOTE_CLASS = r"[\"'""''`´]"

# 섹션 패턴(국영문 병기, 우선순위가 높은 순으로 나열)
SECTION_PATTERNS_PRIORITIZED = [
    (
        "검토 내용",
        r"(검토\s?내용|세부\s?검토|검토사항|기술\s?검토|review|assessment)",
    ),
    (
        "비교 대안",
        r"(비교\s?대안|대안\s?비교|대안|옵션|alternatives?|options?)",
    ),
    (
        "선정 사유",
        r"(선정\s?사유|채택\s?사유|선정\s?기준|rationale|reason)",
    ),
    (
        "예산/비용",
        r"(예산|비용|금액|단가|총액|견적|원가|budget|cost|price|amount|total)",
    ),
    (
        "배경/목적",
        r"(배경|목적|background|objective|purpose)",
    ),
    (
        "현황",
        r"(현황|현\s*상태|상태|운영\s*현황|장비\s*현황|status|current\s*state)",
    ),
    (
        "리스크",
        r"(리스크|위험|한계|제약|이슈|risk|limitation|constraint|issue)",
    ),
    (
        "일정/계획",
        r"(일정|타임라인|계획|로드맵|schedule|timeline|plan|roadmap)",
    ),
]

# 고위험 상세 키워드 문맥 패턴 (동사와 결합될 때만 true)
_DETAIL_CONTEXT_PATTERNS = [
    r"(전부|모두|전체)\s*(보여|알려|출력|정리|표시)",
    r"풀로\s*(보여|알려|출력|정리|표시)",
]


def _apply_canon_maps(s: str) -> str:
    """표기 변형 표준화 적용

    Args:
        s: 정규화할 문자열

    Returns:
        표준화된 문자열
    """
    for pat, rep in _CANON_MAP.items():
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    for pat, rep in _KO_CANON_MAP.items():
        s = re.sub(pat, rep, s)
    return s


def normalize_query(q: str) -> str:
    """쿼리 정규화: 공백/어미/강조/표기 변형 흡수

    Args:
        q: 원본 쿼리

    Returns:
        정규화된 쿼리

    정규화 순서:
    1. 소문자화 + 공백 압축
    2. 한국어 '자세히/상세히' 변형 수렴
    3. 영문/한글 표기 변형 표준화
    4. 따옴표류 통일

    예:
        "FullVer PLEASE!!" → "full version please!!"
        "풀-버젼 자세하게요" → "풀버전 자세히"
        "비교 대안  자세히좀" → "비교 대안 자세히"
    """
    s = (q or "").strip().lower()
    s = re.sub(r"\s+", " ", s)

    # 한국어 '자세히/상세히' 변형 수렴: (자|상)세(히|하게)(요|좀)? → (자|상)세히
    s = re.sub(r"(자|상)세(히|하게)(요|좀)?", lambda m: f"{m.group(1)}세히", s)

    # 영문/한글 표기 변형 표준화
    s = _apply_canon_maps(s)

    # 따옴표류 통일
    s = re.sub(_QUOTE_CLASS, '"', s)

    return s


def is_detailed_mode(q: str, extra_keywords: Optional[List[str]] = None) -> bool:
    """상세 답변 모드 감지(과검출 절제: 고위험 키워드는 문맥 패턴으로만)

    Args:
        q: 원본 쿼리
        extra_keywords: 추가 키워드 (프로젝트별 확장용)

    Returns:
        상세 모드 여부

    로직:
    1. 안전 키워드(DETAIL_KEYWORDS_BASE): 단순 포함으로 판단
    2. 고위험 키워드(전부/모두/전체/풀로): 문맥 패턴과 결합될 때만 True

    예:
        "이 문서 전부 보여줘" → True (문맥 패턴 매칭)
        "2024년 소모품 검토서 전체 목록" → False (문맥 동사 없음)
        "자세히 알려줘" → True (안전 키워드)
        "full version please" → True (안전 키워드)
    """
    nq = normalize_query(q)
    kws = set(k.lower() for k in (DETAIL_KEYWORDS_BASE + (extra_keywords or [])))

    # 안전 키워드: 단순 포함으로 판단
    if any(kw in nq for kw in kws):
        return True

    # 고위험 키워드: 문맥 패턴과 결합될 때만 True
    if any(re.search(p, nq) for p in _DETAIL_CONTEXT_PATTERNS):
        return True

    return False


def detect_section(q: str) -> Optional[str]:
    """섹션 앵커 감지(우선순위 기반 단일 반환)

    Args:
        q: 원본 쿼리

    Returns:
        감지된 섹션명 또는 None

    우선순위:
    1. 검토 내용 (가장 구체적)
    2. 비교 대안
    3. 선정 사유
    4. 예산/비용
    5. 배경/목적
    6. 현황
    7. 리스크
    8. 일정/계획

    예:
        "비교 대안 자세히" → "비교 대안"
        "Show me budget summary" → "예산/비용"
        "검토 내용과 비용" → "검토 내용" (우선순위 높음)
    """
    nq = normalize_query(q)
    for sec, pat in SECTION_PATTERNS_PRIORITIZED:
        if re.search(pat, nq, flags=re.IGNORECASE):
            return sec
    return None
