"""응답 빌더 모듈

RAG 응답 생성에 필요한 유틸리티 함수들.
pipeline.py의 유틸리티 함수들을 모듈화.

Strangler Fig 패턴:
    1단계: pipeline.py에서 이 모듈의 함수들을 import하여 사용
    2단계: 점진적으로 로직 이동
    3단계: pipeline.py는 facade만 유지
"""

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.core.logging import get_logger
from app.utils.sqlite_helpers import connect_metadata
from config.constants import ResponseBuilderConfig

logger = get_logger(__name__)


# ============================================================================
# 상수 정의 (정규식 패턴만 - 다른 모듈에서 import됨)
# ============================================================================

# 컴파일된 정규식 패턴 (모듈 로드 시 1회 컴파일)
RE_SIMPLE_MATH = re.compile(r"^\s*\d+\s*[\+\-\*/]\s*\d+\s*(=\s*\d+)?\s*[은?]*\s*$")
RE_UI_TAG = re.compile(r"🏷[^·]+·\s*")
RE_UI_DATE = re.compile(r"📅[^·]+·\s*")
RE_UI_AUTHOR = re.compile(r"✍[^·]+")
RE_PDF_SPACE = re.compile(r"\s+pdf\s+")
RE_MULTI_SPACE = re.compile(r"\s+")
RE_PAGE_TAG = re.compile(r"\[페이지\s*\d+\]")
RE_OCR_TAG = re.compile(r"\[OCR[^\]]*\]")
RE_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}_")
RE_PDF_EXT = re.compile(r"\.pdf$", re.IGNORECASE)
RE_YEAR_EXTRACT = re.compile(r"(\d{4})-")


# ============================================================================
# 쿼리 분류 함수들 (query_routing.py에서 import하여 재노출)
# ============================================================================

# 순환 참조 방지: 런타임 import
def is_smalltalk(query: str) -> bool:
    """스몰토크/인사/감탄사 감지 (query_routing으로 위임)"""
    from app.rag.query_routing import is_smalltalk as _is_smalltalk
    return _is_smalltalk(query)


def is_simple_math(query: str) -> bool:
    """단순 산술 질의 감지 (query_routing으로 위임)"""
    from app.rag.query_routing import is_simple_math as _is_simple_math
    return _is_simple_math(query)


def has_domain_keyword(query: str) -> bool:
    """도메인 키워드 포함 여부 확인 (query_routing으로 위임)"""
    from app.rag.query_routing import has_domain_keyword as _has_domain_keyword
    return _has_domain_keyword(query)


def force_chat_mode(query: str) -> tuple:
    """강제 CHAT 모드 적용 여부 판단 (query_routing으로 위임)"""
    from app.rag.query_routing import force_chat_mode as _force_chat_mode
    return _force_chat_mode(query)


# ============================================================================
# UI/텍스트 정리 함수들
# ============================================================================

def clean_ui_metadata(query: str) -> str:
    """UI에서 복사한 메타데이터 태그 제거"""
    original = query

    # 컴파일된 패턴들로 제거
    query = RE_UI_TAG.sub("", query)
    query = RE_UI_DATE.sub("", query)
    query = RE_UI_AUTHOR.sub("", query)
    query = RE_PDF_SPACE.sub(" ", query)
    query = RE_MULTI_SPACE.sub(" ", query).strip()

    if query != original:
        logger.info(
            f"🧹 UI 메타데이터 제거: '{original[:60]}...' → '{query[:60]}...'",
        )

    return query


def normalize_chunk_text(result: dict[str, Any]) -> str:
    """청크 텍스트 정규화 (snippet/content/text 통일)"""
    return (
        result.get("snippet") or
        result.get("content") or
        result.get("text") or
        ""
    ).lower()


def clean_text_preview(text: str) -> str:
    """텍스트 미리보기에서 노이즈 제거 및 핵심 내용 추출"""
    clean = RE_PAGE_TAG.sub("", text)
    clean = RE_OCR_TAG.sub("", clean)

    # 0. 검토서 양식: 첫 줄이 제목 (기술관리팀 보도기술관리파트 / 작성일 이전)
    review_match = re.search(
        r"^(.+?(?:검토|교체|분석|계획|방안|보고))\s*(?:기술관리팀|작성일|\d+\.\s*개요)",
        clean
    )
    if review_match:
        title = review_match.group(1).strip()
        if len(title) > 5 and "기안서" not in title:
            return title[:ResponseBuilderConfig.TEXT_PREVIEW_MAX_LEN]

    # 1. "제목" 이후 실제 제목만 추출 (제목 끝 패턴으로 종료)
    title_match = re.search(
        r"제\s*목\s+(.+?(?:의\s*건|검토서?|요청서?|보고서?|계획서?|결과서?|현황|안내))",
        clean
    )
    if title_match:
        title = title_match.group(1).strip()
        if len(title) > 5:
            return title[:ResponseBuilderConfig.TEXT_PREVIEW_MAX_LEN]

    # 2. "제목" 이후 숫자.내용 이전까지만 추출
    title_match2 = re.search(r"제\s*목\s+(.+?)(?=\s*\d+\.\s*)", clean)
    if title_match2:
        title = title_match2.group(1).strip()
        if len(title) > 5:
            return title[:ResponseBuilderConfig.TEXT_PREVIEW_MAX_LEN]

    # 3. 형식적 텍스트 패턴 제거 (fallback)
    form_patterns = [
        r"기안서\([^)]*\)",
        r"장비구매/수리>?\s*기안서",
        r"업무협조전",
        r"CHANNEL\s*MEDIATECH",
        r"Channel\s*MEDIATECH",
        r"기술관리팀[-\s]*보도기술관리파트[-\s]*\d*",
        r"문서번호[^제]*",
        r"신청구분[^제]*",
        r"기안부서[^제]*",
        r"시행일자[^제]*",
        r"기안자[^제]*",
        r"기안일자[^제]*",
        r"기안일[^제]*",
        r"보존기간\s*\d+년",
        r"파트장\s*팀장\s*대표이사",
        r"결재\s*합의",
        r"기결",
        r"수신및참조자?[^제]*",
        r"\d{4}[-./]\d{1,2}[-./]\d{1,2}\s*~?\s*\d{0,4}[-./]?\d{0,2}[-./]?\d{0,2}",
        r"\d{1,2}:\d{2}",
        r"[-\d]+00\d+",
    ]

    for pattern in form_patterns:
        clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)

    # 다중 공백 정리
    clean = RE_MULTI_SPACE.sub(" ", clean).strip()

    # 앞부분 불필요한 문자 제거
    clean = re.sub(r"^[\s\-\d./]+", "", clean)

    max_len = ResponseBuilderConfig.TEXT_PREVIEW_MAX_LEN
    return clean[:max_len] if len(clean) > max_len else clean


# ============================================================================
# 파일/경로 관련 함수들
# ============================================================================

def format_title_from_filename(filename: str) -> str:
    """파일명에서 제목 추출"""
    title = RE_DATE_PREFIX.sub("", filename)
    title = RE_PDF_EXT.sub("", title)
    return title.replace("_", " ")


def build_file_path(filename: str) -> str:
    """파일명에서 경로 생성"""
    year_match = RE_YEAR_EXTRACT.search(filename)
    if year_match:
        year = year_match.group(1)
        return f"docs/year_{year}/{filename}"
    return f"docs/{filename}"


def _generate_file_token(filename: str) -> str:
    """파일명 기반 해시 토큰 생성 (내부 헬퍼)"""
    hash_len = ResponseBuilderConfig.FILE_REF_TOKEN_LEN
    return f"doc:{hashlib.sha1(filename.encode()).hexdigest()[:hash_len]}"


def encode_file_ref(filename: str) -> Optional[str]:
    """파일명을 토큰(해시)으로 변환

    Args:
        filename: 파일명

    Returns:
        doc:{hash} 형식 토큰 또는 None

    Note:
        경로를 base64로 노출하지 않고 해시 토큰 사용
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

    except sqlite3.OperationalError as e:
        logger.warning(f"⚠️ DB 일시 오류 (ref 토큰): {filename} - {e}")
    except sqlite3.Error as e:
        logger.error(f"❌ DB 오류 (ref 토큰): {filename} - {e}", exc_info=True)
    except OSError as e:
        logger.warning(f"⚠️ 파일 시스템 오류 (ref 토큰): {filename} - {e}")
    except Exception as e:
        logger.exception(f"❌ ref 토큰 생성 예상치 못한 오류: {filename} - {type(e).__name__}")

    return None


# ============================================================================
# 키워드 분석 함수들 (query_routing.py로 위임)
# ============================================================================

def get_keyword_coverage(query: str, results: list[dict]) -> int:
    """쿼리와 검색 결과 간 도메인 키워드 교집합 개수 계산 (query_routing으로 위임)"""
    from app.rag.query_routing import get_keyword_coverage as _get_keyword_coverage
    return _get_keyword_coverage(query, results)


# ============================================================================
# Evidence 빌더 함수들
# ============================================================================

def build_evidence_item(
    filename: str,
    snippet: str = "",
    page: int = 1,
    drafter: Optional[str] = None,
    date: Optional[str] = None,
    category: Optional[str] = None,
    doctype: Optional[str] = None,
    claimed_total: Optional[int] = None,
) -> dict[str, Any]:
    """단일 Evidence 아이템 생성"""
    file_path = build_file_path(filename)
    ref = encode_file_ref(filename)

    return {
        "doc_id": filename,
        "filename": filename,
        "file_path": file_path,
        "page": page,
        "snippet": snippet[:ResponseBuilderConfig.EVIDENCE_SNIPPET_MAX_LEN] if snippet else "",
        "ref": ref,
        "meta": {
            "filename": filename,
            "drafter": drafter,
            "date": date,
            "category": category,
            "doctype": doctype,
            "claimed_total": claimed_total,
        },
    }


def build_evidence_list(
    doc_details: list[dict[str, Any]],
    retriever=None,
) -> list[dict[str, Any]]:
    """Evidence 목록 생성

    Args:
        doc_details: 문서 상세 정보 리스트
        retriever: 스니펫 폴백용 retriever (선택)

    Returns:
        Evidence 목록
    """
    evidence = []

    for doc in doc_details:
        filename = doc.get("filename", "")
        snippet = doc.get("text_preview", "").strip()
        title = format_title_from_filename(filename)

        # 스니펫 폴백 체인
        if not snippet and retriever:
            try:
                chunks = retriever.search(filename, top_k=1)
                if chunks:
                    chunk_text = normalize_chunk_text(chunks[0])
                    snippet = chunk_text[:ResponseBuilderConfig.EVIDENCE_SNIPPET_MAX_LEN] if chunk_text else ""
            except (AttributeError, KeyError) as e:
                logger.debug(f"⚠️ BM25 청크 폴백 실패 ({filename}): {e}")
            except Exception as e:
                logger.warning(f"⚠️ BM25 청크 폴백 예상치 못한 오류 ({filename}): {type(e).__name__}")

        if not snippet:
            snippet = title[:ResponseBuilderConfig.FALLBACK_TITLE_MAX_LEN]

        evidence.append(build_evidence_item(
            filename=filename,
            snippet=snippet,
            drafter=doc.get("drafter"),
            date=doc.get("date"),
            category=doc.get("category"),
            doctype=doc.get("doctype"),
            claimed_total=doc.get("claimed_total"),
        ))

    return evidence


# ============================================================================
# 응답 포맷팅 함수들
# ============================================================================

def format_search_card(
    index: int,
    filename: str,
    drafter: str = "",
    date: str = "",
    doctype: str = "",
    claimed_total: Optional[int] = None,
    text_preview: str = "",
) -> str:
    """검색 결과 카드 포맷팅 (2025-12-11: 깔끔한 형식으로 개선)"""
    title = format_title_from_filename(filename)
    lines = [f"{index}. {title}"]

    # 메타데이터 한 줄로 표시 (날짜 | 기안자 | 금액)
    EMPTY_VALUES = {None, "", "None", "없음", "정보 없음", "기타", "작성자 미상", "날짜 없음"}
    meta_parts = []
    if date and date not in EMPTY_VALUES:
        meta_parts.append(f"📅 {date}")
    if drafter and drafter not in EMPTY_VALUES:
        meta_parts.append(f"👤 {drafter}")
    if claimed_total:
        meta_parts.append(f"💰 {claimed_total:,}원")

    if meta_parts:
        lines.append("   " + " | ".join(meta_parts))

    return "\n".join(lines)


def format_search_results(
    keywords: str,
    doc_details: list[dict[str, Any]],
    is_count_query: bool = False,
) -> str:
    """검색 결과 전체 포맷팅"""
    cards = []
    for i, doc in enumerate(doc_details, 1):
        card = format_search_card(
            index=i,
            filename=doc.get("filename", ""),
            drafter=doc.get("drafter", "작성자 미상"),
            date=doc.get("date", "날짜 없음"),
            doctype=doc.get("doctype", "문서"),
            claimed_total=doc.get("claimed_total"),
            text_preview=doc.get("text_preview", ""),
        )
        cards.append(card)

    if is_count_query:
        card_limit = ResponseBuilderConfig.COUNT_QUERY_CARD_LIMIT
        text = f"**'{keywords}' 관련 문서는 총 {len(doc_details)}개**입니다.\n\n"
        text += "\n\n".join(cards[:card_limit])
        if len(cards) > card_limit:
            text += f"\n\n... 외 {len(cards) - card_limit}개 문서"
    else:
        text = f"📄 **'{keywords}' 관련 문서 ({len(doc_details)}건)**\n\n"
        text += "\n\n".join(cards)

    return text


def build_standard_response(
    mode: str,
    text: str,
    files: list[str],
    count: int,
    citations: Optional[list[dict[str, Any]]] = None,
    found: bool = True,
    retrieved_count: Optional[int] = None,
    selected_count: Optional[int] = None,
) -> dict[str, Any]:
    """표준 응답 딕셔너리 생성"""
    citations = citations or []
    retrieved_count = retrieved_count if retrieved_count is not None else count
    selected_count = selected_count if selected_count is not None else count

    return {
        "mode": mode,
        "text": text,
        "files": files,
        "count": count,
        "citations": citations,
        "evidence": citations,  # 하위 호환
        "status": {
            "retrieved_count": retrieved_count,
            "selected_count": selected_count,
            "found": found,
        },
    }


def build_error_response(mode: str, error: str) -> dict[str, Any]:
    """에러 응답 생성"""
    return build_standard_response(
        mode=mode,
        text=f"오류: {error}",
        files=[],
        count=0,
        found=False,
    )


def build_empty_response(mode: str, message: str) -> dict[str, Any]:
    """빈 결과 응답 생성"""
    return build_standard_response(
        mode=mode,
        text=message,
        files=[],
        count=0,
        found=False,
    )
