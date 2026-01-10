"""쿼리 처리 모듈

검색 쿼리에서 키워드 추출, 필터 감지, 쿼리 타입 분류 등을 담당.
search.py에서 분리된 SRP 적용 모듈.

2025-12-22: search.py 리팩토링으로 분리
"""

import re
import sqlite3
from typing import Optional

from app.core.logging import get_logger
from config.constants import HandlerConfig

logger = get_logger(__name__)


# ============================================================================
# 상수 정의
# ============================================================================

# 불용어 목록
STOP_WORDS = [
    "문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘",
]

# 정밀 검색용 추가 불용어
CONTENT_STOP_WORDS = [
    "내용", "본문", "들어간", "포함", "포함된", "있는", "만",
]

# 조사 (단어 경계에서만 제거)
POSTPOSITIONS = [" 에 ", " 에서 ", " 이 ", " 가 ", " 을 ", " 를 "]

# 개수 질의 키워드 (constants.py에서 임포트)
COUNT_KEYWORDS = HandlerConfig.COUNT_KEYWORDS

# 리스트/전체 질의 키워드
# 2026-01-10: "현황", "상태", "종류" 추가 (목록 의도 강화)
LIST_KEYWORDS = ["리스트", "목록", "보여", "현황", "상태", "종류"]
ALL_KEYWORDS = ["전부", "모두", "모든", "전체", "all", "어떤", "뭐", "어떤 것"]

# 시간순 정렬 요청 키워드 (2025-12-25: 최신 이력 우선 답변)
# 2025-12-26: "현황", "현재", "상태", "지금" 추가 (검색 최신성 편향 해결)
TEMPORAL_KEYWORDS = [
    "언제", "이력", "최근", "최신", "히스토리", "history",
    "작년", "올해", "금년", "전년도", "지난해",
    "내역", "과거", "예전", "이전",
    "현황", "현재", "상태", "지금",  # 추가
]

# 명시적 리스트 키워드
# 2026-01-10: "현황", "장애 현황", "모니터 현황", "상태" 추가
EXPLICIT_LIST_KEYWORDS = {
    "리스트", "목록", "전체 목록", "all",
    "현황", "장애 현황", "모니터 현황", "상태",
}

# 상세 요청 감지 키워드
DETAIL_INDICATORS = {"1)", "2)", "3)", "내용", "부분만", "요약", "설명", "자세히"}

# 대량 검색 패턴
BULK_PATTERNS = [
    r"(전부|모두|모든).*(알려|보여|찾아)",
    r"(알려|보여|찾아).*(전부|모두)",
]

# 폴백 기안자 목록
_FALLBACK_DRAFTERS = [
    "유인혁", "최새름", "하승범", "신규호", "노규민", "남준수",
    "이권형", "이승현", "윤상현", "장다운", "정다운", "김승룡",
    "총무팀", "강병규", "박연수", "이호영", "이승헌", "이의주",
]

# 기안자 목록 캐시
_DRAFTERS_CACHE: list[str] | None = None


# ============================================================================
# 기안자 로드
# ============================================================================

def get_common_drafters() -> list[str]:
    """DB에서 기안자 목록을 동적으로 로드 (캐싱 적용)"""
    global _DRAFTERS_CACHE
    if _DRAFTERS_CACHE is not None:
        return _DRAFTERS_CACHE

    try:
        conn = sqlite3.connect("metadata.db")
        rows = conn.execute(
            "SELECT DISTINCT drafter FROM documents WHERE drafter IS NOT NULL AND drafter != ''"
        ).fetchall()
        conn.close()
        _DRAFTERS_CACHE = [row[0] for row in rows if row[0]]
        logger.info(f"기안자 목록 로드: {len(_DRAFTERS_CACHE)}명")

    except sqlite3.OperationalError as e:
        logger.warning(f"기안자 목록 로드 실패 (DB 일시 오류), 폴백 사용: {e}")
        _DRAFTERS_CACHE = _FALLBACK_DRAFTERS

    except sqlite3.Error as e:
        logger.warning(f"기안자 목록 로드 실패 (DB 오류), 폴백 사용: {e}")
        _DRAFTERS_CACHE = _FALLBACK_DRAFTERS

    except Exception as e:
        logger.warning(f"기안자 목록 로드 실패 ({type(e).__name__}), 폴백 사용: {e}")
        _DRAFTERS_CACHE = _FALLBACK_DRAFTERS

    return _DRAFTERS_CACHE


# ============================================================================
# 쿼리 정제 함수
# ============================================================================

def clean_query(query: str) -> str:
    """쿼리에서 이모지, 특수문자, UI 형식 제거

    웹 UI에서 복사한 문서 제목 형식을 정리:
    - 이모지 제거 (📅, 👤, ✅ 등)
    - UI 구분자 제거 (|)
    - 연속 공백 정리
    """
    # 이모지 제거 (유니코드 이모지 범위)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 이모티콘
        "\U0001F300-\U0001F5FF"  # 기호 및 픽토그램
        "\U0001F680-\U0001F6FF"  # 교통 및 지도
        "\U0001F1E0-\U0001F1FF"  # 국기
        "\U00002702-\U000027B0"  # 딩뱃
        "\U0001F900-\U0001F9FF"  # 보조 기호
        "\U0001FA00-\U0001FA6F"  # 체스 기호
        "\U0001FA70-\U0001FAFF"  # 기호 확장
        "\U00002600-\U000026FF"  # 기타 기호
        "]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub(" ", query)

    # UI 구분자 제거
    cleaned = cleaned.replace("|", " ")

    # 연속 공백을 단일 공백으로
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()


def extract_keywords(query: str, stop_words: list[str]) -> str:
    """쿼리에서 불용어를 제거하고 키워드 추출

    Args:
        query: 사용자 원본 쿼리
        stop_words: 제거할 불용어 목록

    Returns:
        불용어가 제거된 키워드 문자열
    """
    # 먼저 이모지/특수문자 정리
    keywords = clean_query(query)

    # 불용어 제거
    for word in stop_words:
        keywords = keywords.replace(word, " ")

    # 연속 공백 정리
    keywords = re.sub(r"\s+", " ", keywords)

    return keywords.strip()


# ============================================================================
# 필터 추출 함수
# ============================================================================

def extract_drafter_filter(query: str) -> Optional[str]:
    """쿼리에서 기안자명 추출

    Args:
        query: 사용자 쿼리

    Returns:
        추출된 기안자명. 없으면 None
    """
    for name in get_common_drafters():
        if name in query:
            logger.info(f"🔍 기안자 필터 적용: {name}")
            return name
    return None


def extract_year_filter(query: str) -> Optional[str]:
    """쿼리에서 연도 추출

    Args:
        query: 사용자 쿼리

    Returns:
        추출된 연도 문자열 (예: "2024"). 없으면 None
    """
    year_match = re.search(r"(20\d{2})년?", query)
    if year_match:
        year = year_match.group(1)
        logger.info(f"📅 연도 필터 적용: {year}")
        return year
    return None


# ============================================================================
# 쿼리 타입 판별 함수
# ============================================================================

def is_readable_text(text: str) -> bool:
    """텍스트가 읽을 수 있는지 확인 (OCR 노이즈 필터링)

    Args:
        text: 검사할 텍스트

    Returns:
        True면 읽기 가능한 텍스트
    """
    if not text or len(text.strip()) < 10:
        return False

    # 한글 비율 확인
    korean_chars = len(re.findall(r"[가-힣]", text))
    total_chars = len(re.findall(r"\S", text))

    if total_chars == 0:
        return False

    korean_ratio = korean_chars / total_chars

    # 한글 비율이 낮으면 (15% 미만) 노이즈일 가능성
    if korean_ratio < 0.15:
        return False

    return True


def is_count_query(query: str) -> bool:
    """개수를 묻는 쿼리인지 확인

    Args:
        query: 사용자 쿼리

    Returns:
        True면 개수 쿼리
    """
    return any(kw in query for kw in COUNT_KEYWORDS)


def is_list_query(query: str) -> bool:
    """리스트/목록/현황을 요청하는 쿼리인지 확인 (2026-01-10 개선)

    Args:
        query: 사용자 쿼리

    Returns:
        True면 리스트 쿼리

    Examples:
        >>> is_list_query("티비로직 모니터 장애 현황 알려줘")
        True
        >>> is_list_query("검토한 대안은 뭐가 있어?")
        True
        >>> is_list_query("모니터 상태는?")
        True
        >>> is_list_query("총 비용은 얼마?")
        False
    """
    query_lower = query.lower()

    # 명시적 목록 키워드
    if any(kw in query_lower for kw in EXPLICIT_LIST_KEYWORDS):
        return True

    # LIST_KEYWORDS 확인 (기존 로직 유지)
    if any(kw in query_lower for kw in LIST_KEYWORDS):
        return True

    # "현황 + 알려줘/보여줘/말해줘" 패턴
    if "현황" in query_lower and any(verb in query_lower for verb in ["알려", "보여", "말해"]):
        return True

    # "장애 + 목록성 동사" 패턴
    if "장애" in query_lower and any(verb in query_lower for verb in ["어떤", "뭐가", "전부", "모두"]):
        return True

    # "상태 + 질문" 패턴
    if "상태" in query_lower and any(verb in query_lower for verb in ["어때", "알려", "보여"]):
        return True

    return False


def is_all_query(query: str) -> bool:
    """전체를 요청하는 쿼리인지 확인

    Args:
        query: 사용자 쿼리

    Returns:
        True면 전체 쿼리
    """
    return any(kw in query for kw in ALL_KEYWORDS)


def is_temporal_query(query: str) -> bool:
    """시간순 정렬이 필요한 쿼리인지 확인 (2025-12-25)

    "언제", "이력", "최근" 등의 키워드가 있으면
    검색 결과를 날짜 역순(최신순)으로 정렬해야 함

    Args:
        query: 사용자 쿼리

    Returns:
        True면 시간순 정렬 필요

    Examples:
        >>> is_temporal_query("무선 마이크는 언제 수리했어?")
        True
        >>> is_temporal_query("무선 마이크 최근 수리 이력")
        True
        >>> is_temporal_query("무선 마이크 문서 찾아줘")
        False
    """
    return any(kw in query for kw in TEMPORAL_KEYWORDS)


def needs_expanded_search(query: str, drafter_filter: Optional[str]) -> bool:
    """확장 검색이 필요한지 확인 (대량 결과 예상)

    Args:
        query: 사용자 쿼리
        drafter_filter: 기안자 필터

    Returns:
        True면 확장 검색 필요
    """
    # 기안자 필터가 있으면 해당 기안자의 전체 문서를 원할 가능성
    if drafter_filter:
        return True

    # 리스트/전체 키워드
    if is_list_query(query) or is_all_query(query):
        return True

    # 대량 검색 패턴
    for pattern in BULK_PATTERNS:
        if re.search(pattern, query):
            return True

    return False


def calculate_max_docs(query: str, drafter_filter: Optional[str]) -> int:
    """쿼리 특성에 따른 최대 문서 수 계산

    Args:
        query: 사용자 쿼리
        drafter_filter: 기안자 필터

    Returns:
        최대 문서 수
    """
    from config.constants import HandlerConfig

    # 기안자 필터가 있으면 확장
    if drafter_filter:
        return HandlerConfig.SEARCH_DRAFTER_LIMIT

    # 리스트/전체 쿼리
    if is_list_query(query) or is_all_query(query):
        return HandlerConfig.SEARCH_LIST_LIMIT

    # 기본값
    return HandlerConfig.SEARCH_DEFAULT_LIMIT


# ============================================================================
# 공개 API (하위 호환성)
# ============================================================================

# 조사 (단어 경계에서만 제거)
POSTPOSITIONS = [" 에 ", " 에서 ", " 이 ", " 가 ", " 을 ", " 를 "]


__all__ = [
    # 상수
    "STOP_WORDS",
    "CONTENT_STOP_WORDS",
    "POSTPOSITIONS",
    "COUNT_KEYWORDS",
    "LIST_KEYWORDS",
    "ALL_KEYWORDS",
    "EXPLICIT_LIST_KEYWORDS",
    "DETAIL_INDICATORS",
    "BULK_PATTERNS",
    # 함수
    "get_common_drafters",
    "clean_query",
    "extract_keywords",
    "extract_drafter_filter",
    "extract_year_filter",
    "is_readable_text",
    "is_count_query",
    "is_list_query",
    "is_all_query",
    "needs_expanded_search",
    "calculate_max_docs",
]
