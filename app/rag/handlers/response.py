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
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.utils.sqlite_helpers import connect_metadata
from app.rag.utils.text import get_query_token_count

logger = get_logger(__name__)


# ============================================================================
# 상수 정의
# ============================================================================

# 스몰토크 패턴
SMALLTALK_PATTERNS = {
    'hi', 'hello', 'hey',
    '안녕', '안녕하세요', '안녕하십니까',
    '감사', '고마워', '감사합니다', '고마워요',
    'thanks', 'thank you',
    'bye', 'goodbye', '잘가', '안녕히',
}

# 도메인 키워드
DOMAIN_KEYWORDS = {
    # 장비
    'nvr', 'sync', 'eco8000', 'lvm-180a', 'odin', 'vmix', 'faiss',
    'tri-level', 'sdi', 'lut', 'intercom', 'di box', 'dibox',
    '무선마이크', '마이크', '카메라', '렌즈', '삼각대', '케이블',
    '건전지', '배터리', '소모품', '장비', '중계차',
    # 프로젝트/프로그램
    '돌직구쇼', '뉴스', '스튜디오', '광화문', '오픈스튜디오',
    '중계', '방송', '채널에이',
    # 기술/문서
    '기안서', '구매', '수리', '교체', '검토', '기술검토',
    '오버홀', '도입', '노후화', '단종',
    '작성', '작성된', '문서', '리스트', '목록',
    # 작성자 (실제 기안자 이름)
    '최새름', '유인혁', '남준수', '박준서', '이원구',
    '최정은', '한건희', '김경현', '김수연', '김창수', '송경원',
}


# ============================================================================
# 쿼리 분류 함수들
# ============================================================================

def is_smalltalk(query: str) -> bool:
    """스몰토크/인사/감탄사 감지"""
    s = query.strip().lower()

    # 1. 직접 패턴 일치
    if s in SMALLTALK_PATTERNS:
        return True

    # 2. 정규식 패턴
    smalltalk_regex = (
        r'^(안녕|안녕하세요|안녕하십니까|감사합니다?|고마워요?|'
        r'thanks|thank you|hi|hello|hey|bye|goodbye|잘가|안녕히)[.!?\s]*$'
    )
    if re.fullmatch(smalltalk_regex, s):
        return True

    return False


def is_simple_math(query: str) -> bool:
    """단순 산술 질의 감지"""
    q_stripped = query.strip()
    math_pattern = r'^\s*\d+\s*[\+\-\*/]\s*\d+\s*(=\s*\d+)?\s*[은?]*\s*$'
    return bool(re.match(math_pattern, q_stripped))


def has_domain_keyword(query: str) -> bool:
    """도메인 키워드 포함 여부 확인"""
    q_lower = query.lower()
    for keyword in DOMAIN_KEYWORDS:
        if keyword in q_lower:
            return True
    return False


# get_query_token_count → app.rag.utils.text에서 import


def force_chat_mode(query: str) -> tuple:
    """강제 CHAT 모드 적용 여부 판단

    Returns:
        (should_force, reason)
    """
    # 1. 스몰토크
    if is_smalltalk(query):
        return True, "smalltalk"

    # 2. 단순 산술
    if is_simple_math(query):
        return True, "simple_math"

    # 3. 짧은 질의 (토큰 < 3) - 단, 도메인 키워드가 있으면 제외
    tokens = get_query_token_count(query)
    if tokens < 3 and not has_domain_keyword(query):
        return True, "short_query"

    return False, ""


# ============================================================================
# UI/텍스트 정리 함수들
# ============================================================================

def clean_ui_metadata(query: str) -> str:
    """UI에서 복사한 메타데이터 태그 제거"""
    original = query

    # 패턴들 제거
    query = re.sub(r'🏷[^·]+·\s*', '', query)
    query = re.sub(r'📅[^·]+·\s*', '', query)
    query = re.sub(r'✍[^·]+', '', query)
    query = re.sub(r'\s+pdf\s+', ' ', query)
    query = re.sub(r'\s+', ' ', query).strip()

    if query != original:
        logger.info(
            f"🧹 UI 메타데이터 제거: '{original[:60]}...' → '{query[:60]}...'"
        )

    return query


def normalize_chunk_text(result: Dict[str, Any]) -> str:
    """청크 텍스트 정규화 (snippet/content/text 통일)"""
    return (
        result.get("snippet") or
        result.get("content") or
        result.get("text") or
        ""
    ).lower()


def clean_text_preview(text: str) -> str:
    """텍스트 미리보기에서 노이즈 제거"""
    clean = re.sub(r'\[페이지\s*\d+\]', '', text)
    clean = re.sub(r'\[OCR[^\]]*\]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


# ============================================================================
# 파일/경로 관련 함수들
# ============================================================================

def format_title_from_filename(filename: str) -> str:
    """파일명에서 제목 추출"""
    title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
    title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
    return title.replace('_', ' ')


def build_file_path(filename: str) -> str:
    """파일명에서 경로 생성"""
    year_match = re.search(r'(\d{4})-', filename)
    if year_match:
        year = year_match.group(1)
        return f"docs/year_{year}/{filename}"
    return f"docs/{filename}"


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
                (filename,)
            )
            result = cursor.fetchone()

        if result and result[0]:
            token = hashlib.sha1(filename.encode()).hexdigest()[:10]
            return f"doc:{token}"

        # 2. Fallback: docs 폴더 검색
        year_match = re.search(r'(\d{4})-', filename)
        if year_match:
            year = year_match.group(1)
            file_path = Path(f"docs/year_{year}") / filename
            if file_path.exists():
                token = hashlib.sha1(filename.encode()).hexdigest()[:10]
                return f"doc:{token}"

        # 3. Fallback2: docs 폴더 전체 검색
        docs_dir = Path("docs")
        if docs_dir.exists():
            for file_path in docs_dir.rglob(filename):
                if file_path.is_file():
                    token = hashlib.sha1(filename.encode()).hexdigest()[:10]
                    return f"doc:{token}"

    except Exception as e:
        logger.warning(f"ref 토큰 생성 실패: {filename} - {e}")

    return None


# ============================================================================
# 키워드 분석 함수들
# ============================================================================

def get_keyword_coverage(query: str, results: List[Dict]) -> int:
    """쿼리와 검색 결과 간 도메인 키워드 교집합 개수 계산"""
    q_lower = query.lower()
    query_keywords = {kw for kw in DOMAIN_KEYWORDS if kw in q_lower}

    if not query_keywords:
        return 0

    found_keywords = set()
    for result in results[:10]:
        chunk_text = normalize_chunk_text(result)
        for kw in query_keywords:
            if kw in chunk_text:
                found_keywords.add(kw)

    return len(found_keywords)


# ============================================================================
# Evidence 빌더 함수들
# ============================================================================

def build_evidence_item(
    filename: str,
    snippet: str = "",
    page: int = 1,
    drafter: str = None,
    date: str = None,
    category: str = None,
    doctype: str = None,
    claimed_total: int = None
) -> Dict[str, Any]:
    """단일 Evidence 아이템 생성"""
    file_path = build_file_path(filename)
    ref = encode_file_ref(filename)

    return {
        "doc_id": filename,
        "filename": filename,
        "file_path": file_path,
        "page": page,
        "snippet": snippet[:400] if snippet else "",
        "ref": ref,
        "meta": {
            "filename": filename,
            "drafter": drafter,
            "date": date,
            "category": category,
            "doctype": doctype,
            "claimed_total": claimed_total
        }
    }


def build_evidence_list(
    doc_details: List[Dict[str, Any]],
    retriever=None
) -> List[Dict[str, Any]]:
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
                    snippet = chunk_text[:400] if chunk_text else ""
            except Exception as e:
                logger.debug(f"⚠️ BM25 청크 폴백 실패 ({filename}): {e}")

        if not snippet:
            snippet = title[:160]

        evidence.append(build_evidence_item(
            filename=filename,
            snippet=snippet,
            drafter=doc.get("drafter"),
            date=doc.get("date"),
            category=doc.get("category"),
            doctype=doc.get("doctype"),
            claimed_total=doc.get("claimed_total")
        ))

    return evidence


# ============================================================================
# 응답 포맷팅 함수들
# ============================================================================

def format_search_card(
    index: int,
    filename: str,
    drafter: str = "작성자 미상",
    date: str = "날짜 없음",
    doctype: str = "문서",
    claimed_total: int = None,
    text_preview: str = ""
) -> str:
    """검색 결과 카드 포맷팅"""
    title = format_title_from_filename(filename)

    lines = [f"{index}. **{title}**"]
    lines.append(f"   📋 {doctype} | 📅 {date} | ✍ {drafter}")

    if claimed_total:
        lines.append(f"   💰 {claimed_total:,}원")

    if text_preview:
        clean_text = clean_text_preview(text_preview)
        if clean_text:
            preview = clean_text[:80]
            lines.append(f"   📝 {preview}...")

    return "\n".join(lines)


def format_search_results(
    keywords: str,
    doc_details: List[Dict[str, Any]],
    is_count_query: bool = False
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
            text_preview=doc.get("text_preview", "")
        )
        cards.append(card)

    if is_count_query:
        text = f"**'{keywords}' 관련 문서는 총 {len(doc_details)}개**입니다.\n\n"
        text += "\n\n".join(cards[:10])
        if len(cards) > 10:
            text += f"\n\n... 외 {len(cards) - 10}개 문서"
    else:
        text = f"📄 **'{keywords}' 관련 문서 ({len(doc_details)}건)**\n\n"
        text += "\n\n".join(cards)

    return text


def build_standard_response(
    mode: str,
    text: str,
    files: List[str],
    count: int,
    citations: List[Dict[str, Any]] = None,
    found: bool = True,
    retrieved_count: int = None,
    selected_count: int = None
) -> Dict[str, Any]:
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
            "found": found
        }
    }


def build_error_response(mode: str, error: str) -> Dict[str, Any]:
    """에러 응답 생성"""
    return build_standard_response(
        mode=mode,
        text=f"오류: {error}",
        files=[],
        count=0,
        found=False
    )


def build_empty_response(mode: str, message: str) -> Dict[str, Any]:
    """빈 결과 응답 생성"""
    return build_standard_response(
        mode=mode,
        text=message,
        files=[],
        count=0,
        found=False
    )
