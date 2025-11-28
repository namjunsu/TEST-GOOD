"""텍스트 처리 유틸리티

중복 코드 제거를 위해 통합된 텍스트 처리 함수들.
pipeline.py, handlers/response.py에서 공통 사용.
"""

import re
from typing import Any

# 도메인 키워드 (장비/프로젝트/기술 용어)
DOMAIN_KEYWORDS: set[str] = {
    # 장비
    "nvr", "sync", "eco8000", "lvm-180a", "odin", "vmix", "faiss",
    "tri-level", "sdi", "lut", "intercom", "di box", "dibox",
    "무선마이크", "마이크", "카메라", "렌즈", "삼각대", "케이블",
    "건전지", "배터리", "소모품", "장비", "중계차",
    # 프로젝트/프로그램
    "돌직구쇼", "뉴스", "스튜디오", "광화문", "오픈스튜디오",
    "중계", "방송", "채널에이",
    # 기술/문서
    "기안서", "구매", "수리", "교체", "검토", "기술검토",
    "오버홀", "도입", "노후화", "단종",
    "작성", "작성된", "문서", "리스트", "목록",
    # 작성자 (실제 기안자 이름)
    "최새름", "유인혁", "남준수", "박준서", "이원구",
    "최정은", "한건희", "김경현", "김수연", "김창수", "송경원",
}


def get_query_token_count(query: str) -> int:
    """간이 토큰 카운트 (한글/영문/숫자/기호 분리)

    Args:
        query: 입력 쿼리

    Returns:
        토큰 개수
    """
    tokens = re.findall(r"[A-Za-z0-9\-_/]+|[가-힣]+", query)
    return len(tokens)


def get_keyword_coverage(query: str, results: list[dict[str, Any]]) -> int:
    """쿼리와 검색 결과 간 도메인 키워드 교집합 개수 계산

    Args:
        query: 사용자 쿼리
        results: 검색 결과 리스트

    Returns:
        매칭된 도메인 키워드 개수
    """
    query_lower = query.lower()
    query_keywords = {kw for kw in DOMAIN_KEYWORDS if kw in query_lower}

    if not query_keywords:
        return 0

    covered = 0
    for r in results:
        text = (r.get("snippet") or r.get("content") or r.get("text") or "").lower()
        for kw in query_keywords:
            if kw in text:
                covered += 1
                break  # 결과당 1회만 카운트

    return covered


def norm_chunk_text(r: dict[str, Any]) -> str:
    """청크 텍스트 정규화 (snippet/content/text 통일)

    Args:
        r: 검색 결과 딕셔너리

    Returns:
        정규화된 텍스트 (소문자)
    """
    return (r.get("snippet") or r.get("content") or r.get("text") or "").lower()


__all__ = [
    "DOMAIN_KEYWORDS",
    "get_keyword_coverage",
    "get_query_token_count",
    "norm_chunk_text",
]
