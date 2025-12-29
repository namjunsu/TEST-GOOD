"""
쿼리 라우터 모델 정의

QueryMode, RouteDecision, ScoreStats 등 라우팅 관련 데이터 클래스.

2025-11-28: query_router.py에서 분리
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ScoreStats:
    """검색 결과 점수 통계"""

    top1: float
    top2: float
    top3: float
    delta12: float
    delta13: float
    ratio12: float  # top1 / max(top2, 1e-9)
    hits: int


class QueryMode(Enum):
    """쿼리 모드 (단순화: 8개 → 7개)

    2025-12-26: COMPREHENSIVE_REPORT 추가
    - 여러 문서를 종합하여 표/리포트 생성
    - "현황 표로 정리", "종합해서 보여줘" 같은 요청

    2025-11-19: SEARCH_CONTENT_ONLY 추가
    - 사용자가 "내용에 X 들어간 문서만" 요청 시 정밀 검색 모드
    - QueryExpander, 파일명/메타데이터 가중치 비활성화
    - BM25 기반 본문 일치만 반환

    2025-11-07: 모드 구조 재설계
    - DOC_ANCHORED 제거 (과도한 필드 추출 문제)
    - PREVIEW + SUMMARY → DOCUMENT 통합
    - LIST + SEARCH + LIST_FIRST → SEARCH 통합
    """

    COST = "cost"  # 비용 조회 (renamed from COST_SUM)
    DOCUMENT = "document"  # 문서 내용/요약 (통합: PREVIEW + SUMMARY)
    SEARCH = "search"  # 문서 검색 (통합: LIST + SEARCH + LIST_FIRST)
    SEARCH_CONTENT_ONLY = "search_content_only"  # 정밀 내용 검색 (본문 일치만)
    QA = "qa"  # 질답 모드 (RAG 파이프라인, 기본)
    YEAR_SUMMARY = "year_summary"  # 연도별 다중 문서 요약 (2025-12-23 추가)
    COMPREHENSIVE_REPORT = "comprehensive_report"  # 종합 리포트 생성 (2025-12-26 추가)


@dataclass
class RouteDecision:
    """쿼리 라우팅 결정 (모드 + 의도 플래그)

    2025-11-10: 모드와 의도를 분리하여 파이프라인 동작을 명확화
    - mode: 5개 모드 (COST, DOCUMENT, SEARCH, SEARCH_CONTENT_ONLY, QA)
    - intent flags: 각 모드 내에서 세부 동작 결정
    - 예: SEARCH + list_intent=True → LLM 건너뛰고 목록 스키마 반환
    """

    mode: QueryMode
    reason: str
    confidence: float

    # 의도 플래그
    list_intent: bool = False  # 목록 반환 의도 (리스트, 목록, 전부, 모든)
    content_intent: bool = False  # 내용 반환 의도 (요약, 미리보기, 내용)
    cost_intent: bool = False  # 비용 조회 의도 (총액, 금액, 얼마)

    # 추출된 파라미터 (필터링용)
    drafter: Optional[str] = None  # 기안자 이름
    year: Optional[int] = None  # 연도 (YYYY)
    date_range: Optional[tuple[str, str]] = None  # 날짜 범위 (시작, 끝)

    # 정렬 기준 (최신순, 오래된순 등)
    sort_by: Optional[list[str]] = None  # ["date_desc"], ["date_asc"] 등
