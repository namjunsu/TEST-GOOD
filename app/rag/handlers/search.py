"""검색 핸들러 모듈

SEARCH, SEARCH_CONTENT_ONLY, COST_SUM 모드를 처리하는 핸들러.
pipeline.py의 _answer_search, _answer_search_content_only, _answer_cost_sum을 위임받아 처리.

Strangler Fig 패턴:
    1단계: pipeline.py의 메서드들이 이 핸들러를 호출
    2단계: 점진적으로 로직 이동
    3단계: pipeline.py는 facade만 유지
"""

import re
import sqlite3
from typing import TYPE_CHECKING, Any, Optional

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
    "문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘"
]

# 정밀 검색용 추가 불용어
CONTENT_STOP_WORDS = [
    "내용", "본문", "들어간", "포함", "포함된", "있는", "만"
]

# 조사 (단어 경계에서만 제거)
POSTPOSITIONS = [" 에 ", " 에서 ", " 이 ", " 가 ", " 을 ", " 를 "]

# 자주 등장하는 기안자 목록
COMMON_DRAFTERS = [
    "남준수", "최새름", "유인혁", "이의주", "강병규", "박연수", "이호영", "이승헌"
]

# 개수 질의 키워드
COUNT_KEYWORDS = ["몇개", "몆개", "몇 개", "몆 개", "개수", "총", "몇", "몆"]

# 리스트/전체 질의 키워드
LIST_KEYWORDS = ["리스트", "목록", "보여", "알려"]
ALL_KEYWORDS = ["전부", "모두", "모든", "전체", "all"]

# 명시적 리스트 키워드
EXPLICIT_LIST_KEYWORDS = {"리스트", "목록", "전체 목록", "all"}

# 상세 요청 감지 키워드
DETAIL_INDICATORS = {"1)", "2)", "3)", "내용", "부분만", "요약", "설명", "자세히"}

# 대량 검색 패턴
BULK_PATTERNS = [
    r"(전부|모두|모든).*(알려|보여|찾아)",
    r"(알려|보여|찾아).*(전부|모두)"
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
    for name in COMMON_DRAFTERS:
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
                f"{f' | 연도={year_filter}' if year_filter else ''}"
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
                    keywords, drafter_filter, year_filter
                )

            # 6. 문서 상세 정보 조회
            max_docs = calculate_max_docs(query, drafter_filter)
            doc_details = self._get_doc_details(
                filenames[:max_docs], drafter_filter, year_filter
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
            return self._make_error_response(f"문서 검색 중 오류가 발생했습니다: {str(e)}")

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
                expanded_query, top_k=50, strict_content=True
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
                        "found": False
                    }
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
                "text": f"검색 중 오류가 발생했습니다: {str(e)}",
                "files": [],
                "count": 0,
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
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
        year_filter: Optional[str]
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
                "found": total_count > 0
            }
        }

    def _get_doc_details(
        self,
        filenames: list[str],
        drafter_filter: Optional[str],
        year_filter: Optional[str]
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
                    "text_preview": doc.get("text_preview", "")[:400]
                })
            elif not drafter_filter:
                # 필터 없을 때만 메타데이터 없는 문서 포함
                doc_details.append({
                    "filename": filename,
                    "drafter": "작성자 미상",
                    "date": "날짜 없음",
                    "doctype": "문서",
                    "claimed_total": None,
                    "text_preview": ""
                })

        return doc_details

    def _get_content_only_details(self, filenames: list[str]) -> list[dict[str, Any]]:
        """정밀 검색용 문서 상세 정보 조회"""
        doc_details = []
        conn = self._db._get_conn()

        for filename in filenames:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE filename = ? LIMIT 1",
                [filename]
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
                    "path": doc.get("path", "")
                })

        return doc_details

    def _build_search_response(
        self,
        keywords: str,
        query: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str]
    ) -> dict[str, Any]:
        """검색 응답 생성"""
        # 카드 생성
        cards = []
        for i, doc in enumerate(doc_details, 1):
            title = format_title_from_filename(doc["filename"])

            card_lines = [f"{i}. **{title}**"]
            card_lines.append(
                f"   📋 {doc['doctype']} | 📅 {doc['date']} | ✍ {doc['drafter']}"
            )

            if doc["claimed_total"]:
                card_lines.append(f"   💰 {doc['claimed_total']:,}원")

            if doc["text_preview"]:
                clean_text = clean_text_preview(doc["text_preview"])
                if clean_text:
                    preview = clean_text[:80]
                    card_lines.append(f"   📝 {preview}...")

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

        return {
            "mode": "SEARCH",
            "text": answer_text,
            "files": filenames,
            "count": len(doc_details),
            "citations": evidence,
            "evidence": evidence,
            "status": {
                "retrieved_count": len(doc_details),
                "selected_count": len(doc_details),
                "found": True
            }
        }

    def _build_content_only_response(
        self,
        keywords: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str]
    ) -> dict[str, Any]:
        """정밀 검색 응답 생성"""
        response_text = f"📄 **'{keywords}' 내용 포함 문서 ({len(doc_details)}건)**\n\n"

        for i, doc in enumerate(doc_details, 1):
            title = doc["title"] or doc["filename"]
            category_emoji = "📋" if "기안서" in doc["category"] else "📄"
            drafter_str = f"✍ {doc['drafter']}" if doc["drafter"] else ""
            date_str = f"📅 {doc['date']}" if doc["date"] else ""

            meta_parts = [
                p for p in [category_emoji + " " + doc["category"], date_str, drafter_str]
                if p
            ]
            meta_line = " | ".join(meta_parts)

            response_text += f"**{i}.** {title}\n"
            if meta_line:
                response_text += f"   {meta_line}\n"

            if doc["claimed_total"]:
                response_text += f"   💰 {doc['claimed_total']:,}원\n"

            if doc["text_preview"]:
                response_text += f"   📝 {doc['text_preview']}...\n"

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
                    "category": doc["category"]
                }
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
                "found": len(citations) > 0
            }
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
                    "doctype": doc.get("doctype")
                }
            })

        return evidence


class CostSumHandler(BaseHandler):
    """비용 합계 핸들러

    COST_SUM 모드를 처리합니다.
    DB의 claimed_total 컬럼을 활용하여 비용 합계를 조회합니다.
    """

    mode = "COST_SUM"

    def __init__(self, pipeline: "RAGPipeline"):
        super().__init__(pipeline)
        self._db = MetadataDB()

    def handle(self, query: str, **kwargs) -> dict[str, Any]:
        """COST_SUM 모드 쿼리 처리"""
        try:
            # 1. 검색으로 후보 문서 찾기
            search_results = self.retriever.search(query, top_k=15)

            if not search_results:
                logger.warning(f"비용 질의 검색 실패: {query}")
                return {
                    "mode": self.mode,
                    "text": "관련 문서를 찾을 수 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 2. DB에서 claimed_total 수집
            cost_docs = []
            for result in search_results:
                filename = result.get("meta", {}).get("filename") or result.get("doc_id", "")
                if not filename:
                    continue

                doc = self._db.get_by_filename(filename)
                if doc and doc.get("claimed_total"):
                    cost_docs.append((doc["claimed_total"], doc, filename))

            if not cost_docs:
                logger.warning("검색된 문서에 비용 정보 없음")
                return {
                    "mode": self.mode,
                    "text": "검색된 문서에 비용 합계 정보가 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": len(search_results),
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 3. 금액 내림차순 정렬
            cost_docs.sort(key=lambda x: x[0], reverse=True)

            # 4. 응답 생성
            return self._build_cost_response(cost_docs, len(search_results))

        except sqlite3.Error as e:
            logger.error(f"❌ DB 오류: {e}", exc_info=True)
            return self._make_error_response("비용 조회 중 데이터베이스 오류가 발생했습니다.")

        except ValueError as e:
            logger.error(f"❌ 금액 파싱 오류: {e}", exc_info=True)
            return self._make_error_response("금액 정보 파싱 중 오류가 발생했습니다.")

        except Exception as e:
            logger.error(f"❌ 비용 질의 처리 실패: {e}", exc_info=True)
            return self._make_error_response(f"비용 정보 조회 중 오류가 발생했습니다: {str(e)}")

    def _build_cost_response(
        self,
        cost_docs: list[tuple],
        retrieved_count: int
    ) -> dict[str, Any]:
        """비용 응답 생성"""
        total_sum = sum(doc[0] for doc in cost_docs)
        evidence = []
        filenames = []

        if len(cost_docs) == 1:
            # 단일 문서
            claimed_total, doc, filename = cost_docs[0]
            text_preview = doc.get("text_preview", "")
            vat_status = "VAT 별도" if "VAT" in text_preview or "부가세" in text_preview else "VAT 포함 추정"

            sum_match = doc.get("sum_match")
            if sum_match is None:
                verification = "sum_match=없음"
            elif sum_match:
                verification = "sum_match=일치 ✅"
            else:
                verification = "sum_match=불일치 ⚠️"

            answer_text = f"💰 합계: **₩{claimed_total:,}** ({vat_status})\n"
            answer_text += f"출처: {filename} | 날짜: {doc.get('display_date') or doc.get('date') or '정보 없음'} | 기안자: {doc.get('drafter') or '정보 없음'}\n"
            answer_text += f"검증: {verification}"

            filenames = [filename]
            evidence = [{
                "doc_id": filename,
                "filename": filename,
                "page": 1,
                "snippet": f"비용 합계: ₩{claimed_total:,}",
                "ref": None,
                "meta": {
                    "filename": filename,
                    "drafter": doc.get("drafter"),
                    "date": doc.get("display_date") or doc.get("date"),
                    "claimed_total": claimed_total
                }
            }]

            logger.info(f"💰 비용 질의 성공 (단일): {filename} → ₩{claimed_total:,}")

        else:
            # 복수 문서
            answer_text = f"💰 **총 {len(cost_docs)}건 문서 비용 합계: ₩{total_sum:,}**\n\n"
            answer_text += "**상세 내역:**\n"

            for i, (claimed_total, doc, filename) in enumerate(cost_docs[:10], 1):
                title = format_title_from_filename(filename)

                answer_text += f"{i}. {title}: ₩{claimed_total:,}\n"
                answer_text += f"   📅 {doc.get('display_date') or doc.get('date') or '날짜 없음'} | ✍ {doc.get('drafter') or '정보 없음'}\n"

                filenames.append(filename)
                evidence.append({
                    "doc_id": filename,
                    "filename": filename,
                    "page": 1,
                    "snippet": f"비용 합계: ₩{claimed_total:,}",
                    "ref": None,
                    "meta": {
                        "filename": filename,
                        "drafter": doc.get("drafter"),
                        "date": doc.get("display_date") or doc.get("date"),
                        "claimed_total": claimed_total
                    }
                })

            if len(cost_docs) > 10:
                answer_text += f"\n... 외 {len(cost_docs) - 10}건 (합계에 포함)"

            logger.info(f"💰 비용 질의 성공 (복수): {len(cost_docs)}건 → 총 ₩{total_sum:,}")

        return {
            "mode": self.mode,
            "text": answer_text,
            "files": filenames,
            "count": len(cost_docs),
            "citations": evidence,
            "evidence": evidence,
            "status": {
                "retrieved_count": retrieved_count,
                "selected_count": len(cost_docs),
                "found": True
            }
        }
