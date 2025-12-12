"""검색 핸들러 모듈

SEARCH, SEARCH_CONTENT_ONLY 모드를 처리하는 핸들러.
pipeline.py의 _answer_search, _answer_search_content_only를 위임받아 처리.

COST_SUM 모드는 cost_sum.py로 분리됨 (SRP 적용).

Strangler Fig 패턴:
    1단계: pipeline.py의 메서드들이 이 핸들러를 호출
    2단계: 점진적으로 로직 이동
    3단계: pipeline.py는 facade만 유지
"""

import re
import sqlite3
from typing import TYPE_CHECKING, Any, Optional, TypedDict

from app.core.errors import SearchError
from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from config.constants import HandlerConfig

from .base import BaseHandler
from .response import (
    build_file_path,
    clean_text_preview,
    format_title_from_filename,
)

if TYPE_CHECKING:
    from app.rag.pipeline import RAGPipeline

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

# 빈 값으로 간주할 값들 (UI 표시 시 필터링)
EMPTY_VALUES = frozenset({None, "", "None", "없음", "정보 없음", "기타", "작성자 미상", "날짜 없음"})


# ============================================================================
# 타입 정의
# ============================================================================

class DocDetail(TypedDict, total=False):
    """문서 상세 정보 타입"""
    filename: str
    drafter: str
    date: str
    doctype: str
    claimed_total: int | None
    text_preview: str
    title: str
    category: str
    path: str


class SearchStatus(TypedDict):
    """검색 상태 타입"""
    retrieved_count: int
    selected_count: int
    found: bool
    merged_similar: int  # 선택적


class EvidenceItem(TypedDict, total=False):
    """증거 항목 타입"""
    doc_id: str
    filename: str
    file_path: str
    page: int
    snippet: str
    ref: str | None
    meta: dict[str, Any]


# 기안자 목록 캐시 (앱 시작 시 DB에서 로드)
_DRAFTERS_CACHE: list[str] | None = None


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
    except Exception as e:
        logger.warning(f"기안자 목록 로드 실패, 폴백 사용: {e}")
        # 폴백: 기본 목록
        _DRAFTERS_CACHE = [
            "유인혁", "최새름", "하승범", "신규호", "노규민", "남준수",
            "이권형", "이승현", "윤상현", "장다운", "정다운", "김승룡",
            "총무팀", "강병규", "박연수", "이호영", "이승헌", "이의주",
        ]
    return _DRAFTERS_CACHE

# 개수 질의 키워드
COUNT_KEYWORDS = ["몇개", "몆개", "몇 개", "몆 개", "개수", "총", "몇", "몆"]

# 리스트/전체 질의 키워드 (2025-12-09: "알려" 제거 - 정보 질의 의도와 리스트 요청 구분)
LIST_KEYWORDS = ["리스트", "목록", "보여"]
ALL_KEYWORDS = ["전부", "모두", "모든", "전체", "all"]

# 명시적 리스트 키워드
EXPLICIT_LIST_KEYWORDS = {"리스트", "목록", "전체 목록", "all"}

# 상세 요청 감지 키워드
DETAIL_INDICATORS = {"1)", "2)", "3)", "내용", "부분만", "요약", "설명", "자세히"}

# 대량 검색 패턴
BULK_PATTERNS = [
    r"(전부|모두|모든).*(알려|보여|찾아)",
    r"(알려|보여|찾아).*(전부|모두)",
]


# ============================================================================
# 헬퍼 함수
# ============================================================================

def extract_keywords(query: str, stop_words: list[str]) -> str:
    """쿼리에서 불용어를 제거하고 키워드 추출

    Args:
        query: 사용자 원본 쿼리
        stop_words: 제거할 불용어 목록

    Returns:
        불용어가 제거된 키워드 문자열
    """
    keywords = query
    for word in stop_words:
        keywords = keywords.replace(word, " ")
    return keywords.strip()


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


def is_readable_text(text: str) -> bool:
    """텍스트가 읽을 만한 품질인지 확인 (OCR 품질 필터)

    Args:
        text: 검사할 텍스트

    Returns:
        품질이 좋으면 True, 저품질이면 False

    Notes:
        - MIN_TEXT_LENGTH 미만은 의미 없음
        - MAX_SPECIAL_CHAR_RATIO 초과면 OCR 오류 가능성
        - MIN_KOREAN_CHAR_RATIO 미만이면 깨진 텍스트
    """
    if not text or len(text) < HandlerConfig.MIN_TEXT_LENGTH:
        return False

    # 특수문자 비율 체크
    special_chars = sum(1 for c in text if c in '\\/"\'{}[]|<>_')
    if special_chars / len(text) > HandlerConfig.MAX_SPECIAL_CHAR_RATIO:
        return False

    # 한글 비율 체크
    korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
    if korean_chars / len(text) < HandlerConfig.MIN_KOREAN_CHAR_RATIO:
        return False

    return True


def is_count_query(query: str) -> bool:
    """개수만 묻는 질의인지 확인

    Args:
        query: 사용자 쿼리

    Returns:
        "몇개", "개수" 등이 포함되면 True
    """
    return any(kw in query.lower() for kw in COUNT_KEYWORDS)


def is_list_query(query: str) -> bool:
    """리스트 요청 질의인지 확인

    Args:
        query: 사용자 쿼리

    Returns:
        "리스트", "목록" 등이 포함되면 True
    """
    return any(kw in query.lower() for kw in LIST_KEYWORDS)


def is_all_query(query: str) -> bool:
    """전체 요청 질의인지 확인

    Args:
        query: 사용자 쿼리

    Returns:
        "전부", "모두" 등이 포함되면 True
    """
    return any(kw in query.lower() for kw in ALL_KEYWORDS)


def needs_expanded_search(query: str, drafter_filter: Optional[str]) -> bool:
    """확장 검색이 필요한지 확인

    Args:
        query: 사용자 쿼리
        drafter_filter: 기안자 필터 (있으면 확장 검색)

    Returns:
        전체/리스트 요청이거나 기안자 필터가 있으면 True
    """
    needs_all = is_all_query(query) or is_count_query(query)
    wants_list = is_list_query(query)
    return needs_all or wants_list or bool(drafter_filter)


def calculate_max_docs(query: str, drafter_filter: Optional[str]) -> int:
    """검색할 최대 문서 수 계산

    Args:
        query: 사용자 쿼리
        drafter_filter: 기안자 필터

    Returns:
        BULK_SEARCH_TOP_K(200) 또는 NORMAL_SEARCH_TOP_K(10)
    """
    is_detail = any(ind in query for ind in DETAIL_INDICATORS)
    is_explicit_list = any(kw in query.lower() for kw in EXPLICIT_LIST_KEYWORDS)
    is_bulk = any(re.search(p, query) for p in BULK_PATTERNS)

    wants_list = (is_explicit_list or is_bulk) and not is_detail
    return HandlerConfig.BULK_SEARCH_TOP_K if wants_list or drafter_filter else HandlerConfig.NORMAL_SEARCH_TOP_K


# NOTE: format_title_from_filename, build_file_path, clean_text_preview 함수는
# response.py에서 import하여 사용 (코드 중복 제거)


# ============================================================================
# SearchHandler 클래스
# ============================================================================

class SearchHandler(BaseHandler):
    """문서 검색 핸들러

    SEARCH, SEARCH_CONTENT_ONLY 모드를 처리합니다.

    Modes:
        - SEARCH: 키워드 기반 BM25 검색
        - SEARCH_CONTENT_ONLY: 정밀 내용 검색 (본문에 키워드 포함된 문서만)
    """

    mode = "SEARCH"

    def __init__(self, pipeline: "RAGPipeline"):
        super().__init__(pipeline)
        self._db = MetadataDB()

    def handle(self, query: str, **kwargs) -> dict[str, Any]:
        """SEARCH 모드 쿼리 처리

        Args:
            query: 사용자 쿼리
            **kwargs: 추가 파라미터
                - content_only: True면 정밀 내용 검색

        Returns:
            표준 응답 딕셔너리
        """
        content_only = kwargs.get("content_only", False)

        if content_only:
            return self._handle_content_only(query)
        return self._handle_search(query)

    def _handle_search(self, query: str) -> dict[str, Any]:
        """일반 검색 처리"""
        try:
            # 1. 키워드 및 필터 추출
            keywords = extract_keywords(query, STOP_WORDS)
            drafter_filter = extract_drafter_filter(query)
            year_filter = extract_year_filter(query)

            logger.info(
                f"🔍 문서 검색: 키워드='{keywords}'"
                f"{f' | 기안자={drafter_filter}' if drafter_filter else ''}"
                f"{f' | 연도={year_filter}' if year_filter else ''}",
            )

            # 2. 검색 top_k 결정
            search_top_k = HandlerConfig.BULK_SEARCH_TOP_K if needs_expanded_search(query, drafter_filter) else HandlerConfig.NORMAL_SEARCH_TOP_K
            logger.info(f"🔍 검색 top_k: {search_top_k}")

            # 3. 검색 실행
            if not hasattr(self.retriever, "search"):
                logger.error("❌ Retriever에 search 메서드가 없습니다")
                return self._make_error_response("검색 기능을 사용할 수 없습니다.")

            search_results = self.retriever.search(keywords, top_k=search_top_k)

            # 4. 파일명 추출 (중복 제거)
            filenames = self._extract_unique_filenames(search_results)

            if not filenames:
                return self._make_empty_response(f"'{keywords}' 관련 문서를 찾지 못했습니다.")

            # 5. 개수만 묻는 질의 처리
            if is_count_query(query):
                return self._handle_count_query(
                    keywords, drafter_filter, year_filter,
                )

            # 6. 문서 상세 정보 조회
            max_docs = calculate_max_docs(query, drafter_filter)
            doc_details = self._get_doc_details(
                filenames[:max_docs], drafter_filter, year_filter,
            )

            # 7. 응답 생성
            return self._build_search_response(keywords, query, doc_details, filenames)

        except sqlite3.Error as e:
            logger.error(f"❌ DB 오류: {e}", exc_info=True)
            return self._make_error_response("데이터베이스 접근 중 오류가 발생했습니다.")

        except SearchError as e:
            logger.error(f"❌ 검색 오류: {e}", exc_info=True)
            return self._make_error_response(f"검색 중 오류: {e.message}")

        except Exception as e:
            logger.error(f"❌ 문서 검색 실패: {e}", exc_info=True)
            return self._make_error_response(f"문서 검색 중 오류가 발생했습니다: {e!s}")

    def _handle_content_only(self, query: str) -> dict[str, Any]:
        """정밀 내용 검색 처리 (본문에 키워드 포함된 문서만)"""
        try:
            # 1. 키워드 추출 (불용어 + 조사 제거)
            all_stop_words = STOP_WORDS + CONTENT_STOP_WORDS
            keywords = " " + query + " "
            for word in all_stop_words:
                keywords = keywords.replace(word, " ")
            for postposition in POSTPOSITIONS:
                keywords = keywords.replace(postposition, " ")
            keywords = keywords.strip()

            if not keywords:
                logger.warning("⚠️ 정밀 내용 검색: 불용어 제거 후 키워드가 비어있음")
                return {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": (
                        "⚠️ **정밀 내용 검색을 위해서는 검색할 키워드가 필요합니다.**\n\n"
                        "예시:\n"
                        "- 문서내용에 **티비로직** 들어간 문서만\n"
                        "- 내용에 **SPG9000** 포함된 문서\n"
                        "- 본문에 **ECO8000** 있는 문서만"
                    ),
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False,
                    },
                }

            # 2. 동의어 확장 (QueryExpander 없이 브랜드/모델명 변형 처리)
            try:
                from app.rag.domain_synonyms import expand_for_strict_content
                expanded_query = expand_for_strict_content(keywords)
            except ImportError:
                expanded_query = keywords

            logger.info(f"🎯 정밀 내용 검색: raw='{keywords}', expanded='{expanded_query}'")

            # 3. strict_content=True로 검색
            if not hasattr(self.retriever, "search"):
                return self._make_error_response("검색 기능을 사용할 수 없습니다.")

            search_results = self.retriever.search(
                expanded_query, top_k=50, strict_content=True,
            )

            if not search_results:
                return {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": f"📄 **'{keywords}' 관련 문서 (0건)**\n\n검색 결과가 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False,
                    },
                }

            # 4. 파일명 추출 및 메타데이터 조회
            filenames = self._extract_unique_filenames(search_results)
            doc_details = self._get_content_only_details(filenames[:10])

            # 5. 응답 생성
            return self._build_content_only_response(keywords, doc_details, filenames)

        except Exception as e:
            logger.error(f"❌ 정밀 내용 검색 실패: {e}", exc_info=True)
            return {
                "mode": "SEARCH_CONTENT_ONLY",
                "text": f"검색 중 오류가 발생했습니다: {e!s}",
                "files": [],
                "count": 0,
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False,
                },
            }

    # ========================================================================
    # Private 헬퍼 메서드
    # ========================================================================

    def _extract_unique_filenames(self, search_results: list[dict]) -> list[str]:
        """검색 결과에서 고유 파일명 추출"""
        filenames = []
        seen = set()
        for result in search_results:
            filename = result.get("filename") or result.get("doc_id")
            if filename and filename not in seen:
                filenames.append(filename)
                seen.add(filename)
        return filenames

    def _handle_count_query(
        self,
        keywords: str,
        drafter_filter: Optional[str],
        year_filter: Optional[str],
    ) -> dict[str, Any]:
        """개수만 묻는 질의 처리"""
        conn = self._db._get_conn()
        sql = "SELECT COUNT(*) as cnt FROM documents WHERE 1=1"
        params = []

        if drafter_filter:
            sql += " AND drafter = ?"
            params.append(drafter_filter)

        if year_filter:
            sql += " AND (date LIKE ? OR display_date LIKE ?)"
            params.extend([f"{year_filter}%", f"{year_filter}%"])

        cursor = conn.execute(sql, params)
        total_count = cursor.fetchone()["cnt"]

        drafter_text = f"{drafter_filter} " if drafter_filter else ""
        year_text = f"{year_filter}년 " if year_filter else ""

        return {
            "mode": "SEARCH",
            "text": f"{year_text}{drafter_text}문서는 총 **{total_count}개**입니다.",
            "files": [],
            "count": total_count,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": total_count,
                "selected_count": 0,
                "found": total_count > 0,
            },
        }

    def _get_doc_details(
        self,
        filenames: list[str],
        drafter_filter: Optional[str],
        year_filter: Optional[str],
    ) -> list[dict[str, Any]]:
        """파일명 목록에서 문서 상세 정보 조회"""
        doc_details = []
        conn = self._db._get_conn()

        for filename in filenames:
            sql = "SELECT * FROM documents WHERE filename = ?"
            params = [filename]

            if drafter_filter:
                sql += " AND drafter = ?"
                params.append(drafter_filter)

            if year_filter:
                sql += " AND (date LIKE ? OR display_date LIKE ?)"
                params.extend([f"{year_filter}%", f"{year_filter}%"])

            sql += " LIMIT 1"
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()

            if row:
                doc = dict(row)
                doc_details.append({
                    "filename": filename,
                    "drafter": doc.get("drafter", "작성자 미상"),
                    "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                    "doctype": doc.get("doctype", "문서"),
                    "claimed_total": doc.get("claimed_total"),
                    "text_preview": doc.get("text_preview", "")[:400],
                })
            elif not drafter_filter:
                # 필터 없을 때만 메타데이터 없는 문서 포함
                doc_details.append({
                    "filename": filename,
                    "drafter": "작성자 미상",
                    "date": "날짜 없음",
                    "doctype": "문서",
                    "claimed_total": None,
                    "text_preview": "",
                })

        return doc_details

    def _get_content_only_details(self, filenames: list[str]) -> list[dict[str, Any]]:
        """정밀 검색용 문서 상세 정보 조회"""
        doc_details = []
        conn = self._db._get_conn()

        for filename in filenames:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE filename = ? LIMIT 1",
                [filename],
            )
            row = cursor.fetchone()

            if row:
                doc = dict(row)
                doc_details.append({
                    "filename": filename,
                    "title": doc.get("title", filename),
                    "category": doc.get("category", "기안서"),
                    "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                    "drafter": doc.get("drafter", "작성자 미상"),
                    "claimed_total": doc.get("claimed_total", 0),
                    "text_preview": doc.get("text_preview", "")[:100],
                    "path": doc.get("path", ""),
                })

        return doc_details

    def _build_search_response(
        self,
        keywords: str,
        query: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str],
    ) -> dict[str, Any]:
        """검색 응답 생성"""
        # 카드 생성 (2025-12-11: 깔끔한 형식으로 개선)
        cards = []
        for i, doc in enumerate(doc_details, 1):
            title = format_title_from_filename(doc["filename"])
            card_lines = [f"{i}. {title}"]

            # 메타데이터 한 줄로 표시 (날짜 | 기안자 | 금액)
            meta_parts = []
            if doc.get("date") and doc["date"] not in EMPTY_VALUES:
                meta_parts.append(f"📅 {doc['date']}")
            if doc.get("drafter") and doc["drafter"] not in EMPTY_VALUES:
                meta_parts.append(f"👤 {doc['drafter']}")
            if doc.get("claimed_total"):
                meta_parts.append(f"💰 {doc['claimed_total']:,}원")

            if meta_parts:
                card_lines.append("   " + " | ".join(meta_parts))

            cards.append("\n".join(card_lines))

        # 응답 텍스트 생성
        if is_count_query(query):
            answer_text = f"**'{keywords}' 관련 문서는 총 {len(doc_details)}개**입니다.\n\n"
            answer_text += "\n\n".join(cards[:10])
            if len(cards) > 10:
                answer_text += f"\n\n... 외 {len(cards) - 10}개 문서"
        else:
            answer_text = f"📄 **'{keywords}' 관련 문서 ({len(doc_details)}건)**\n\n"
            answer_text += "\n\n".join(cards)

        # Evidence 생성
        evidence = self._build_evidence(doc_details)

        # 📊 유사 문서 추천 및 병합 (2025-12-08)
        similar_documents = []
        merged_count = 0
        if filenames and hasattr(self.pipeline, '_similarity_service'):
            try:
                # 전체 출처 문서 제외하고 유사 문서 찾기
                all_similar = self.pipeline._similarity_service.find_similar_by_query(
                    query, filenames, top_k=5  # 전체 제외, 여유롭게 검색
                )

                # 유사도 70% 이상은 출처에 병합, 나머지는 유사 문서로 표시
                for sim_doc in all_similar:
                    similarity = sim_doc.get("similarity", 0)
                    if similarity >= 0.7:
                        # 고유사도 문서는 출처에 추가
                        merged_count += 1
                        merged_evidence = {
                            "doc_id": sim_doc["filename"],
                            "filename": sim_doc["filename"],
                            "page": 1,
                            "snippet": f"[유사도 {int(similarity * 100)}%] {sim_doc.get('title', '')}",
                            "file_path": "",
                            "meta": {
                                "filename": sim_doc["filename"],
                                "date": sim_doc.get("date", ""),
                                "drafter": sim_doc.get("drafter", ""),
                                "category": sim_doc.get("category", ""),
                                "is_similar": True,  # 유사 문서 표시
                            },
                        }
                        evidence.append(merged_evidence)
                    else:
                        similar_documents.append(sim_doc)

                if merged_count > 0:
                    logger.info(f"📊 유사 문서 {merged_count}건 출처에 병합됨")

            except Exception as e:
                logger.warning(f"⚠️ 유사 문서 추천 실패 (무시): {e}")

        return {
            "mode": "SEARCH",
            "text": answer_text,
            "files": filenames,
            "count": len(doc_details),
            "citations": evidence,
            "evidence": evidence,
            "similar_documents": similar_documents[:3],  # 📊 유사 문서 추천 (최대 3건)
            "status": {
                "retrieved_count": len(doc_details),
                "selected_count": len(doc_details),
                "found": True,
                "merged_similar": merged_count,  # 병합된 유사 문서 수
            },
        }

    def _build_content_only_response(
        self,
        keywords: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str],
    ) -> dict[str, Any]:
        """정밀 검색 응답 생성 (2025-12-11: 깔끔한 형식으로 개선)"""
        response_text = f"📄 **'{keywords}' 내용 포함 문서 ({len(doc_details)}건)**\n\n"

        for i, doc in enumerate(doc_details, 1):
            title = format_title_from_filename(doc.get("filename", ""))

            # 메타데이터 한 줄로 표시 (날짜 | 기안자 | 금액)
            meta_parts = []
            if doc.get("date") and doc["date"] not in EMPTY_VALUES:
                meta_parts.append(f"📅 {doc['date']}")
            if doc.get("drafter") and doc["drafter"] not in EMPTY_VALUES:
                meta_parts.append(f"👤 {doc['drafter']}")
            if doc.get("claimed_total"):
                meta_parts.append(f"💰 {doc['claimed_total']:,}원")

            response_text += f"{i}. {title}\n"
            if meta_parts:
                response_text += "   " + " | ".join(meta_parts) + "\n"
            response_text += "\n"

        # Citations 생성
        citations = []
        for doc in doc_details:
            citations.append({
                "doc_id": doc["filename"],
                "filename": doc["filename"],
                "page": 1,
                "snippet": doc["text_preview"],
                "file_path": doc["path"],
                "meta": {
                    "filename": doc["filename"],
                    "date": doc["date"],
                    "drafter": doc["drafter"],
                    "category": doc["category"],
                },
            })

        logger.info(f"✅ 정밀 내용 검색 완료: {len(doc_details)}건")

        return {
            "mode": "SEARCH_CONTENT_ONLY",
            "text": response_text,
            "files": filenames[:10],
            "count": len(doc_details),
            "citations": citations,
            "evidence": citations,
            "status": {
                "retrieved_count": len(filenames),
                "selected_count": len(citations),
                "found": len(citations) > 0,
            },
        }

    def _build_evidence(self, doc_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Evidence 목록 생성"""
        evidence = []

        for doc in doc_details:
            filename = doc["filename"]
            file_path = build_file_path(filename)
            title = format_title_from_filename(filename)

            # Snippet 생성
            snippet = doc.get("text_preview", "").strip()
            if not snippet:
                # BM25 청크 폴백 시도
                try:
                    chunks = self.retriever.search(filename, top_k=1)
                    if chunks:
                        chunk_text = chunks[0].get("text", "")
                        snippet = chunk_text[:400] if chunk_text else ""
                except Exception as e:
                    logger.debug(f"⚠️ BM25 청크 폴백 실패 ({filename}): {e}")

            if not snippet:
                snippet = title[:160]

            evidence.append({
                "doc_id": filename,
                "filename": filename,
                "file_path": file_path,
                "page": 1,
                "snippet": snippet[:400],
                "ref": None,
                "meta": {
                    "filename": filename,
                    "drafter": doc.get("drafter"),
                    "date": doc.get("date"),
                    "doctype": doc.get("doctype"),
                },
            })

        return evidence
