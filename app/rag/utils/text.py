"""텍스트 처리 유틸리티

중복 코드 제거를 위해 통합된 텍스트 처리 함수들.
pipeline.py, handlers/response.py에서 공통 사용.

Note:
    DOMAIN_KEYWORDS, get_keyword_coverage는 query_routing.py에서 정의.
    하위 호환성을 위해 re-export만 제공.
"""

import re
from typing import Any


def get_query_token_count(query: str) -> int:
    """간이 토큰 카운트 (한글/영문/숫자/기호 분리)

    Args:
        query: 입력 쿼리

    Returns:
        토큰 개수
    """
    tokens = re.findall(r"[A-Za-z0-9\-_/]+|[가-힣]+", query)
    return len(tokens)


def norm_chunk_text(r: dict[str, Any]) -> str:
    """청크 텍스트 정규화 (snippet/content/text 통일)

    Args:
        r: 검색 결과 딕셔너리

    Returns:
        정규화된 텍스트 (소문자)
    """
    return (r.get("snippet") or r.get("content") or r.get("text") or "").lower()


# ============================================================================
# 하위 호환성 re-export (정규 소스: query_routing.py)
# ============================================================================
# 순환 참조 방지를 위해 지연 import 사용

def get_keyword_coverage(query: str, results: list[dict[str, Any]]) -> int:
    """query_routing.get_keyword_coverage로 위임 (하위 호환성)"""
    from app.rag.query_routing import get_keyword_coverage as _get_keyword_coverage
    return _get_keyword_coverage(query, results)


# 모듈 레벨 __getattr__: DOMAIN_KEYWORDS 지연 로드 (PEP 562)
# 직접 정의하지 않고 query_routing.py에서 가져옴
def __getattr__(name: str):
    """모듈 레벨 속성 지연 로드"""
    if name == "DOMAIN_KEYWORDS":
        from app.rag.query_routing import DOMAIN_KEYWORDS
        return DOMAIN_KEYWORDS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # DOMAIN_KEYWORDS는 __getattr__로 지연 로드 (PEP 562)
    # Ruff F822 회피를 위해 __all__에서 제외하나, from text import DOMAIN_KEYWORDS 여전히 가능
    "get_keyword_coverage",  # 하위 호환성 (query_routing으로 위임)
    "get_query_token_count",
    "norm_chunk_text",
]
