"""쿼리 라우팅 및 헬퍼 함수

이 모듈은 RAG 파이프라인의 라우팅 로직을 담당합니다:
- 스몰토크/산술/도메인 키워드 감지
- 쿼리 라우팅 (모드/섹션/프롬프트 결정)
- UI 메타데이터 클리닝
- 파일 참조 인코딩

의존성: settings, logger, text_normalizer
"""

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.config.settings import settings
from app.core.logging import get_logger
from app.rag.handlers.response import (
    RE_MULTI_SPACE,
    RE_PDF_SPACE,
    RE_SIMPLE_MATH,
    RE_UI_AUTHOR,
    RE_UI_DATE,
    RE_UI_TAG,
    RE_YEAR_EXTRACT,
)
from app.rag.utils.text import get_query_token_count
from app.rag.utils.text import norm_chunk_text as _norm_chunk_text
from app.utils.sqlite_helpers import connect_metadata
from app.utils.text_normalizer import detect_section, is_detailed_mode, normalize_query
from config.constants import QueryRoutingConfig

logger = get_logger(__name__)


# ============================================================================
# 상수 정의
# ============================================================================

# 스몰토크 패턴 (전체 일치 또는 문장 단독 위주)
SMALLTALK_PATTERNS = {
    "hi", "hello", "hey",
    "안녕", "안녕하세요", "안녕하십니까",
    "감사", "고마워", "감사합니다", "고마워요",
    "thanks", "thank you",
    "bye", "goodbye", "잘가", "안녕히",
}

# 일반 대화 패턴 (문서 검색이 아닌 순수 LLM 응답이 필요한 경우)
# Claude/GPT처럼 자연스럽게 대화해야 하는 질문들
GENERAL_CHAT_PATTERNS = [
    # 자기소개/정체성 질문
    re.compile(r"(누구|뭐야|정체|이름|뭐가\s*있어)", re.IGNORECASE),
    re.compile(r"(너는|넌|니가|당신).*(뭐|뭘|무엇|누구)", re.IGNORECASE),
    re.compile(r"(뭐|무엇|어떤\s*것).*(할\s*수\s*있|가능)", re.IGNORECASE),
    # 의견/추천 요청
    re.compile(r"(어떻게\s*생각|의견|추천|조언|제안).*(해|줘|주세요)?", re.IGNORECASE),
    re.compile(r"(좋은|괜찮은|적합한).*(있을까|있어|추천)", re.IGNORECASE),
    # 일반 질문/대화
    re.compile(r"^(뭐해|뭐하고\s*있어|심심해|재밌는\s*거)", re.IGNORECASE),
    re.compile(r"(도와줘|도움|헬프|help)", re.IGNORECASE),
    # 설명 요청 (문서 관련이 아닌 일반 개념)
    re.compile(r"(설명|알려).*(해줘|주세요|줄래)$", re.IGNORECASE),
    # 잡담/감정 표현
    re.compile(r"^(ㅋ+|ㅎ+|ㅠ+|ㅜ+|하하|헤헤|호호|웃기)", re.IGNORECASE),
    re.compile(r"(재밌|웃기|신기|대단|좋아|싫어|멋지)", re.IGNORECASE),
]

# 도메인 키워드 (장비/프로젝트/기술 용어)
DOMAIN_KEYWORDS = {
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

# 진단 모드 설정 (settings 중앙 설정 사용)
DIAG_RAG = settings.DIAG_RAG
DIAG_LOG_LEVEL = settings.DIAG_LOG_LEVEL


# ============================================================================
# 라우팅 헬퍼 함수들
# ============================================================================


def clean_ui_metadata(query: str) -> str:
    """UI에서 복사한 메타데이터 태그 제거 (🏷, 📅, ✍ 등)

    예시:
        입력: "2024 중계차 🏷 pdf · 📅 2024-10-24 · ✍ 문서 내용 요약해 줘"
        출력: "2024 중계차 문서 내용 요약해 줘"
    """
    # 원본 보존 (디버깅용)
    original = query

    # 컴파일된 패턴 사용 (response.py에서 import)
    query = RE_UI_TAG.sub("", query)
    query = RE_UI_DATE.sub("", query)
    query = RE_UI_AUTHOR.sub("", query)
    query = RE_PDF_SPACE.sub(" ", query)
    query = RE_MULTI_SPACE.sub(" ", query).strip()

    # 변경사항이 있으면 로그 출력
    if query != original:
        logger.info(f"🧹 UI 메타데이터 제거: '{original[:60]}...' → '{query[:60]}...'")

    return query


def route_query(query: str) -> dict[str, Any]:
    """쿼리 라우팅: 모드/섹션/프롬프트/리트리버 파라미터 결정

    우선순위:
        1. 상세 모드 (detailed_mode) - 최우선
        2. 섹션 고정 (detected_section)
        3. 요약 모드 (needs_summary)
        4. 기본 Q&A 모드

    Args:
        query: 사용자 질의

    Returns:
        dict: {
            "mode": "DETAILED|SECTION|SUMMARY|QA",
            "prompt_type": 프롬프트 타입,
            "max_tokens": LLM 생성 토큰 수,
            "retriever_params": {
                "top_k": int,
                "chunk_merge": bool,
                "max_context_tokens": int
            },
            "detailed_mode": bool,
            "detected_section": str | None,
            "needs_summary": bool
        }
    """
    # 1) 정규화
    nq = normalize_query(query)

    # 2) 모드/섹션 판단 (상세 모드 우선권)
    detailed = is_detailed_mode(nq)
    section = detect_section(nq)

    # 3) 요약 트리거 (섹션 미지정 & 상세 모드 아님일 때만)
    needs_summary = False
    if not section and not detailed:
        # "내용" 단독은 제외, "요약", "summary" 등 명시적 키워드만
        if any(k in nq for k in ["요약", "summary", "한줄", "한 문장"]):
            needs_summary = True

    # 4) 리트리버 파라미터 (모드별 최적화)
    # - 금액/수치 질문: 관련 청크를 더 많이 가져와서 표 전체 확보
    # - 요약: 문서 전체 맥락 필요
    # - 일반 QA: 정확한 답변을 위해 청크 병합 활성화
    is_numeric_query = any(k in nq for k in ["얼마", "금액", "비용", "합계", "총액", "단가"])

    if detailed:
        retriever_params = {
            "top_k": QueryRoutingConfig.DETAILED_TOP_K,
            "chunk_merge": True,
            "max_context_tokens": QueryRoutingConfig.DETAILED_MAX_CONTEXT,
        }
    elif needs_summary:
        retriever_params = {
            "top_k": QueryRoutingConfig.SUMMARY_TOP_K,
            "chunk_merge": True,
            "max_context_tokens": QueryRoutingConfig.SUMMARY_MAX_CONTEXT,
        }
    elif is_numeric_query:
        # 금액 질문: 표 전체를 가져오기 위해 청크 병합 필수
        retriever_params = {
            "top_k": QueryRoutingConfig.NUMERIC_TOP_K,
            "chunk_merge": True,
            "max_context_tokens": QueryRoutingConfig.NUMERIC_MAX_CONTEXT,
        }
    else:
        # 일반 QA: 청크 병합으로 컨텍스트 연속성 보장
        retriever_params = {
            "top_k": QueryRoutingConfig.QA_MODE_TOP_K,
            "chunk_merge": True,
            "max_context_tokens": QueryRoutingConfig.DEFAULT_MAX_CONTEXT,
        }

    # 5) 프롬프트/토큰 (settings 중앙 설정 사용)
    if detailed:
        mode = "DETAILED"
        prompt_type = "detailed"
        max_tokens = settings.LLM_MAX_TOKENS_DETAILED
    elif section:
        mode = "SECTION"
        prompt_type = "section"
        max_tokens = settings.LLM_MAX_TOKENS_SECTION
    elif needs_summary:
        mode = "SUMMARY"
        prompt_type = "summary"
        max_tokens = settings.LLM_MAX_TOKENS_SUMMARY
    else:
        mode = "QA"
        prompt_type = "qa"
        max_tokens = settings.LLM_MAX_TOKENS_QA

    logger.info(
        f"🎯 라우팅 결정: mode={mode}, detailed={detailed}, section={section}, "
        f"summary={needs_summary}, top_k={retriever_params['top_k']}, "
        f"max_tokens={max_tokens}",
    )

    return {
        "mode": mode,
        "prompt_type": prompt_type,
        "max_tokens": max_tokens,
        "retriever_params": retriever_params,
        "detailed_mode": detailed,
        "detected_section": section,
        "needs_summary": needs_summary,
    }


def is_smalltalk(query: str) -> bool:
    """스몰토크/인사/감탄사 감지 (전체 일치 또는 정규식)"""
    s = query.strip().lower()

    # 1. 직접 패턴 일치 (전체 문장이 스몰토크)
    if s in SMALLTALK_PATTERNS:
        return True

    # 2. 정규식 패턴 (스몰토크만 포함, 구두점 허용)
    smalltalk_regex = (
        r"^(안녕|안녕하세요|안녕하십니까|감사합니다?|고마워요?|thanks|thank you|"
        r"hi|hello|hey|bye|goodbye|잘가|안녕히)[.!?\s]*$"
    )
    if re.fullmatch(smalltalk_regex, s):
        return True

    return False


def is_simple_math(query: str) -> bool:
    """단순 산술 질의 감지 (예: 1+1은?, 2*3=?)"""
    q_stripped = query.strip()
    # 컴파일된 패턴 사용 (response.py에서 import)
    return bool(RE_SIMPLE_MATH.match(q_stripped))


def is_general_chat(query: str) -> bool:
    """일반 대화 감지 (문서 검색이 아닌 순수 LLM 응답이 필요한 경우)

    Claude/GPT처럼 자연스럽게 대화해야 하는 질문 감지:
    - 자기소개/정체성 질문: "넌 뭐야?", "뭐 할 수 있어?"
    - 의견/추천 요청: "어떻게 생각해?", "추천해줘"
    - 일반 질문/잡담: "도와줘", "심심해"
    """
    s = query.strip()

    # 도메인 키워드가 있으면 일반 대화가 아님 (문서 검색 필요)
    if has_domain_keyword(s):
        return False

    # GENERAL_CHAT_PATTERNS 매칭
    for pattern in GENERAL_CHAT_PATTERNS:
        if pattern.search(s):
            return True

    return False


def has_domain_keyword(query: str) -> bool:
    """도메인 키워드 포함 여부 확인

    Note:
        DOMAIN_KEYWORDS는 set이지만, substring 검색이므로 O(n) 순회 필수.
        키워드 수가 적으므로 성능 영향 미미. (현재 ~60개)
    """
    q_lower = query.lower()
    # any()로 첫 매칭 시 즉시 반환 (단축 평가)
    return any(keyword in q_lower for keyword in DOMAIN_KEYWORDS)


def get_keyword_coverage(query: str, results: list) -> int:
    """쿼리와 검색 결과 간 도메인 키워드 교집합 개수 계산

    Args:
        query: 사용자 질문
        results: 검색 결과 리스트

    Returns:
        교집합된 키워드 개수
    """
    q_lower = query.lower()
    # 쿼리에서 매칭된 키워드
    query_keywords = {kw for kw in DOMAIN_KEYWORDS if kw in q_lower}

    if not query_keywords:
        return 0

    # 검색 결과 청크에서 발견된 키워드 (상위 N개)
    found_keywords = set()
    for result in results[:QueryRoutingConfig.KEYWORD_COVERAGE_LIMIT]:
        chunk_text = _norm_chunk_text(result)
        for kw in query_keywords:
            if kw in chunk_text:
                found_keywords.add(kw)

    return len(found_keywords)


def force_chat_mode(query: str) -> tuple[bool, str]:
    """강제 CHAT 모드 적용 여부 판단

    Returns:
        (should_force, reason)

    2025-12-23: 일반 대화 패턴 추가 (Claude/GPT 수준 자연어 이해)
    - 자기소개/정체성 질문
    - 의견/추천 요청
    - 일반 질문/잡담
    """
    # 1. 스몰토크
    if is_smalltalk(query):
        return True, "smalltalk"

    # 2. 단순 산술
    if is_simple_math(query):
        return True, "simple_math"

    # 3. 일반 대화 (2025-12-23 추가)
    # "넌 뭐야?", "뭐 할 수 있어?", "추천해줘" 등
    if is_general_chat(query):
        return True, "general_chat"

    # 4. 짧은 질의 (토큰 < N) - 단, 도메인 키워드가 있으면 제외
    tokens = get_query_token_count(query)
    if tokens < QueryRoutingConfig.SHORT_QUERY_TOKEN_THRESHOLD and not has_domain_keyword(query):
        return True, "short_query"

    return False, ""


def _generate_file_token(filename: str) -> str:
    """파일명 기반 해시 토큰 생성 (내부 헬퍼)"""
    hash_len = QueryRoutingConfig.FILE_REF_HASH_LENGTH
    return f"doc:{hashlib.sha1(filename.encode()).hexdigest()[:hash_len]}"


def _encode_file_ref(filename: str) -> Optional[str]:
    """파일명을 토큰(해시)으로 변환 (보안 강화, 경로 노출 방지)

    Args:
        filename: 파일명

    Returns:
        doc:{hash} 형식 토큰 또는 None

    Note:
        - 경로를 base64로 노출하지 않고 해시 토큰 사용
        - 백엔드에서 /preview?ref=doc:xxx 로 검증 후 제공
    """
    try:
        # 1. metadata.db에서 파일 존재 확인
        with connect_metadata() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT path FROM documents WHERE filename = ? LIMIT 1",
                (filename,),
            )
            result = cursor.fetchone()

        if result and result[0]:
            return _generate_file_token(filename)

        # 2. Fallback: docs 폴더 검색 (연도별)
        year_match = RE_YEAR_EXTRACT.search(filename)
        if year_match:
            year = year_match.group(1)
            file_path = Path(f"docs/year_{year}") / filename
            if file_path.exists():
                return _generate_file_token(filename)

        # 3. Fallback2: docs 폴더 전체 검색
        docs_dir = Path("docs")
        if docs_dir.exists():
            for file_path in docs_dir.rglob(filename):
                if file_path.is_file():
                    return _generate_file_token(filename)

    except sqlite3.Error as e:
        logger.warning(f"⚠️ ref 토큰 DB 오류: {filename} - {e}")
    except OSError as e:
        logger.warning(f"⚠️ ref 토큰 파일 접근 오류: {filename} - {e}")
    except Exception as e:
        logger.warning(f"⚠️ ref 토큰 생성 예상치 못한 오류: {filename} - {type(e).__name__}")

    return None


__all__ = [
    "DIAG_LOG_LEVEL",
    "DIAG_RAG",
    "DOMAIN_KEYWORDS",
    # 상수
    "GENERAL_CHAT_PATTERNS",
    "SMALLTALK_PATTERNS",
    "_encode_file_ref",
    # 함수
    "clean_ui_metadata",
    "force_chat_mode",
    "get_keyword_coverage",
    "has_domain_keyword",
    "is_general_chat",
    "is_simple_math",
    "is_smalltalk",
    "route_query",
]
