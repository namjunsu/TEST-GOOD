"""검색 핸들러 모듈

SEARCH, SEARCH_CONTENT_ONLY 모드를 처리하는 핸들러.
pipeline.py의 _answer_search, _answer_search_content_only를 위임받아 처리.

COST_SUM 모드는 cost_sum.py로 분리됨 (SRP 적용).
쿼리 처리는 query_processor.py로 분리됨.
결과 포맷팅은 result_formatter.py로 분리됨.

Strangler Fig 패턴:
    1단계: pipeline.py의 메서드들이 이 핸들러를 호출
    2단계: 점진적으로 로직 이동
    3단계: pipeline.py는 facade만 유지

2025-12-22: 리팩토링
    - query_processor.py 분리 (쿼리 정제, 필터 추출)
    - result_formatter.py 분리 (응답 빌드, evidence 생성)
"""

import sqlite3
from typing import TYPE_CHECKING, Any, Optional, TypedDict

from app.core.errors import SearchError
from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from config.constants import HandlerConfig

from .base import BaseHandler
from .query_processor import (
    CONTENT_STOP_WORDS,
    POSTPOSITIONS,
    STOP_WORDS,
    calculate_max_docs,
    extract_drafter_filter,
    extract_keywords,
    extract_year_filter,
    is_all_query,
    is_count_query,
    is_list_query,
    is_temporal_query,
    needs_expanded_search,
)
from .response import (
    build_file_path,
    format_title_from_filename,
)
from .result_formatter import EMPTY_VALUES

if TYPE_CHECKING:
    from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


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


# NOTE: 상수 및 헬퍼 함수는 query_processor.py로 분리됨 (2025-12-22)
# NOTE: format_title_from_filename, build_file_path 함수는 response.py에서 import


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

            # 1.5. 스마트 동의어 확장 (YAML 동의어 + 퍼지 매칭)
            try:
                import time
                expand_start = time.perf_counter()
                from app.rag.domain_synonyms import expand_query_smart
                expanded_keywords = expand_query_smart(keywords)
                expand_time = time.perf_counter() - expand_start

                if expanded_keywords != keywords:
                    if expand_time > 5.0:
                        logger.warning(f"⏱️ 쿼리 확장 지연: {expand_time:.2f}s ('{keywords}' → '{expanded_keywords}')")
                    else:
                        logger.info(f"🔄 동의어 확장: '{keywords}' → '{expanded_keywords}' ({expand_time:.3f}s)")
                else:
                    logger.debug(f"⏱️ 쿼리 확장: 변경 없음 ({expand_time:.3f}s)")
            except Exception as e:
                logger.debug(f"동의어 확장 스킵: {e}")
                expanded_keywords = keywords

            # 2. 검색 top_k 결정
            # 2026-01-10: 목록 질문 감지 추가 (현황, 상태 등)
            if is_list_query(query):
                search_top_k = HandlerConfig.BULK_SEARCH_TOP_K
                logger.info(f"📋 목록 질의 감지 → top_k={search_top_k}로 확장 검색")
            elif needs_expanded_search(query, drafter_filter):
                search_top_k = HandlerConfig.BULK_SEARCH_TOP_K
            else:
                search_top_k = HandlerConfig.NORMAL_SEARCH_TOP_K
            logger.info(f"🔍 검색 top_k: {search_top_k}")

            # 3. 검색 실행 (확장된 키워드 사용)
            if not hasattr(self.retriever, "search"):
                logger.error("❌ Retriever에 search 메서드가 없습니다")
                return self._make_error_response("검색 기능을 사용할 수 없습니다.")

            search_results = self.retriever.search(expanded_keywords, top_k=search_top_k)
            logger.info(f"🔎 검색 결과: {len(search_results)}건 반환됨")

            # 4. 파일명 추출 (중복 제거)
            filenames = self._extract_unique_filenames(search_results)
            logger.info(f"✅ 고유 문서: {len(filenames)}건 (중복 제거 완료)")

            # 연도 필터는 _get_doc_details()에서 SQL WHERE 조건으로 처리
            if year_filter:
                logger.info(f"📅 연도 필터 적용 예정: {year_filter}년")

            if not filenames:
                return self._make_empty_response(f"'{keywords}' 관련 문서를 찾지 못했습니다.")

            # 5. 개수만 묻는 질의 처리
            if is_count_query(query):
                return self._handle_count_query(
                    keywords, drafter_filter, year_filter,
                )

            # 5.5 기안자 필터가 있고 결과가 많으면 통계+샘플 응답
            if drafter_filter and len(filenames) > HandlerConfig.DRAFTER_STATS_THRESHOLD:
                return self._handle_drafter_stats(drafter_filter, year_filter, filenames)

            # 6. 문서 상세 정보 조회
            max_docs = calculate_max_docs(query, drafter_filter)
            doc_details = self._get_doc_details(
                filenames[:max_docs], drafter_filter, year_filter,
            )

            # 6.5 시간순 정렬 (2025-12-25: "언제", "이력" 등 키워드 시 최신순 정렬)
            if is_temporal_query(query):
                logger.info("⏰ 시간순 쿼리 감지 → 최신순 정렬 (날짜 역순)")
                doc_details = sorted(
                    doc_details,
                    key=lambda x: x.get("date") or "0000-00-00",
                    reverse=True,  # 최신순 (2024 → 2017)
                )

            # 7. 응답 생성
            # "문서 전부" 또는 "문서들" 요청 시 메타데이터만 표시 (성능 최적화)
            # 2026-01-10: 리스트 쿼리도 metadata_only 처리 (유사도 계산 26분+ 버그 수정)
            is_all_docs_query = is_all_query(query) or is_list_query(query)
            if is_all_docs_query:
                logger.info("⚡ '문서 전부/목록' 요청 감지 → 메타데이터만 표시 (성능 최적화)")
            return self._build_search_response(keywords, query, doc_details, filenames, is_all_docs_query)

        except sqlite3.OperationalError as e:
            # DB 락 또는 연결 문제 - 재시도 가능
            logger.warning(f"⚠️ DB 일시 오류 (검색): {e}")
            return self._make_error_response("데이터베이스가 일시적으로 사용 중입니다. 잠시 후 다시 시도하세요.")

        except sqlite3.Error as e:
            # 기타 DB 오류
            logger.error(f"❌ DB 오류: {e}", exc_info=True)
            return self._make_error_response("데이터베이스 접근 중 오류가 발생했습니다.")

        except SearchError as e:
            # 검색 엔진 오류
            logger.error(f"❌ 검색 오류: {e}", exc_info=True)
            return self._make_error_response(f"검색 중 오류: {e.message}")

        except (AttributeError, KeyError) as e:
            # 인덱스 구조 문제
            logger.error(f"❌ 인덱스 접근 오류: {e}", exc_info=True)
            return self._make_error_response("검색 인덱스 접근 중 오류가 발생했습니다.")

        except Exception as e:
            # 예상치 못한 오류 - 스택트레이스 전체 기록
            logger.exception(f"❌ 문서 검색 예상치 못한 오류: {type(e).__name__}")
            return self._make_error_response(f"문서 검색 중 예상치 못한 오류가 발생했습니다: {type(e).__name__}")

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

            # 2. 스마트 동의어 확장 (YAML 동의어 + 퍼지 매칭)
            try:
                from app.rag.domain_synonyms import expand_query_smart
                expanded_query = expand_query_smart(keywords)
            except ImportError:
                expanded_query = keywords

            logger.info(f"🎯 정밀 내용 검색: raw='{keywords}', expanded='{expanded_query}'")

            # 3. strict_content=True로 검색
            if not hasattr(self.retriever, "search"):
                return self._make_error_response("검색 기능을 사용할 수 없습니다.")

            search_results = self.retriever.search(
                expanded_query, top_k=HandlerConfig.CONTENT_ONLY_TOP_K, strict_content=True,
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
            doc_details = self._get_content_only_details(filenames[:HandlerConfig.CONTENT_ONLY_RESULT_LIMIT])

            # 5. 응답 생성
            return self._build_content_only_response(keywords, doc_details, filenames)

        except sqlite3.OperationalError as e:
            # DB 락 또는 연결 문제
            logger.warning(f"⚠️ DB 일시 오류 (정밀 검색): {e}")
            error_text = "데이터베이스가 일시적으로 사용 중입니다. 잠시 후 다시 시도하세요."

        except sqlite3.Error as e:
            # 기타 DB 오류
            logger.error(f"❌ DB 오류 (정밀 검색): {e}", exc_info=True)
            error_text = "데이터베이스 접근 중 오류가 발생했습니다."

        except SearchError as e:
            # 검색 엔진 오류
            logger.error(f"❌ 검색 오류 (정밀 검색): {e}", exc_info=True)
            error_text = f"검색 중 오류: {e.message}"

        except Exception as e:
            # 예상치 못한 오류
            logger.exception(f"❌ 정밀 내용 검색 예상치 못한 오류: {type(e).__name__}")
            error_text = f"검색 중 예상치 못한 오류가 발생했습니다: {type(e).__name__}"

        return {
            "mode": "SEARCH_CONTENT_ONLY",
            "text": f"❌ {error_text}",
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
            sql += """
                AND (
                    (display_date IS NOT NULL AND display_date LIKE ?)
                    OR (display_date IS NULL AND date IS NOT NULL AND date LIKE ?)
                    OR (display_date IS NULL AND date IS NULL AND year = ?)
                )
            """
            params.extend([f"{year_filter}%", f"{year_filter}%", year_filter])

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

    def _handle_drafter_stats(
        self,
        drafter: str,
        year_filter: Optional[str],
        filenames: list[str],
    ) -> dict[str, Any]:
        """기안자 문서 통계 + 샘플 응답 생성

        많은 문서(>10개)가 있을 때 전체 목록 대신 통계와 샘플을 제공합니다.

        2025-12-21: year_filter가 있으면 해당 연도 문서만 표시하도록 수정
        """
        conn = self._db._get_conn()

        # 1. 총 건수 조회 (연도 필터 적용)
        total_sql = "SELECT COUNT(*) as cnt FROM documents WHERE drafter = ?"
        params: list = [drafter]
        if year_filter:
            total_sql += """
                AND (
                    (display_date IS NOT NULL AND display_date LIKE ?)
                    OR (display_date IS NULL AND date IS NOT NULL AND date LIKE ?)
                    OR (display_date IS NULL AND date IS NULL AND year = ?)
                )
            """
            params.extend([f"{year_filter}%", f"{year_filter}%", year_filter])
        total_count = conn.execute(total_sql, params).fetchone()["cnt"]

        # 2. 연도별 분포 (연도 필터가 있으면 해당 연도만)
        if year_filter:
            # 연도 필터가 있으면 해당 연도 정보만 표시
            year_dist = [{"year": year_filter, "cnt": total_count}]
        else:
            year_sql = """
                SELECT year, COUNT(*) as cnt
                FROM documents
                WHERE drafter = ? AND year IS NOT NULL
                GROUP BY year ORDER BY year DESC
            """
            year_dist = conn.execute(year_sql, [drafter]).fetchall()

        # 3. 카테고리별 분포 (연도 필터 적용)
        cat_sql = """
            SELECT category, COUNT(*) as cnt
            FROM documents
            WHERE drafter = ? AND category IS NOT NULL AND category != '미분류'
        """
        cat_params: list = [drafter]
        if year_filter:
            cat_sql += """
                AND (
                    (display_date IS NOT NULL AND display_date LIKE ?)
                    OR (display_date IS NULL AND date IS NOT NULL AND date LIKE ?)
                    OR (display_date IS NULL AND date IS NULL AND year = ?)
                )
            """
            cat_params.extend([f"{year_filter}%", f"{year_filter}%", year_filter])
        cat_sql += " GROUP BY category ORDER BY cnt DESC LIMIT 10"
        cat_dist = conn.execute(cat_sql, cat_params).fetchall()

        # 4. 최근 문서 (연도 필터 적용)
        recent_sql = """
            SELECT filename, date, category
            FROM documents
            WHERE drafter = ?
        """
        recent_params: list = [drafter]
        if year_filter:
            recent_sql += """
                AND (
                    (display_date IS NOT NULL AND display_date LIKE ?)
                    OR (display_date IS NULL AND date IS NOT NULL AND date LIKE ?)
                    OR (display_date IS NULL AND date IS NULL AND year = ?)
                )
            """
            recent_params.extend([f"{year_filter}%", f"{year_filter}%", year_filter])
        recent_sql += " ORDER BY date DESC LIMIT 5"
        recent_docs = conn.execute(recent_sql, recent_params).fetchall()

        # 5. 응답 텍스트 생성
        year_text = f" **{year_filter}년**" if year_filter else ""
        lines = [f"**{drafter}**님이 기안한{year_text} 문서는 총 **{total_count}건**입니다.\n"]

        # 연도별 분포 (연도 필터가 없을 때만 표시)
        if year_dist and not year_filter:
            lines.append("📊 **연도별 분포:**")
            for row in year_dist:
                lines.append(f"  - {row['year']}년: {row['cnt']}건")
            lines.append("")

        # 카테고리별 분포
        if cat_dist:
            lines.append("📂 **유형별 분포:**")
            for row in cat_dist:
                lines.append(f"  - {row['category']}: {row['cnt']}건")
            lines.append("")

        # 문서 목록 (연도 필터 있으면 "최근" 대신 해당 연도 문서)
        if recent_docs:
            doc_label = f"{year_filter}년 문서" if year_filter else "최근 문서 (5건)"
            lines.append(f"📄 **{doc_label}:**")
            for i, row in enumerate(recent_docs, 1):
                date_str = row["date"] or "날짜 없음"
                fname = row["filename"].replace(".pdf", "")
                lines.append(f"  {i}. {fname} ({date_str})")
            lines.append("")

        # 안내 메시지 (연도 필터 없을 때만)
        if not year_filter:
            lines.append(
                f'💡 더 자세히 보려면: "{drafter} 2024년 문서" 또는 '
                f'"{drafter} 카메라 문서" 처럼 범위를 좁혀서 질문해주세요.'
            )

        return {
            "mode": "SEARCH",
            "text": "\n".join(lines),
            "files": [{"filename": r["filename"]} for r in recent_docs] if recent_docs else [],
            "count": total_count,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": total_count,
                "selected_count": min(5, total_count),
                "found": True,
            },
            "stats": {
                "total": total_count,
                "by_year": {r["year"]: r["cnt"] for r in year_dist},
                "by_category": {r["category"]: r["cnt"] for r in cat_dist},
            },
        }

    def _get_doc_details(
        self,
        filenames: list[str],
        drafter_filter: Optional[str],
        year_filter: Optional[str],
    ) -> list[dict[str, Any]]:
        """파일명 목록에서 문서 상세 정보 조회 (2025-12-21: 배치 쿼리로 최적화)"""
        if not filenames:
            return []

        doc_details = []
        conn = self._db._get_conn()

        # 배치 쿼리로 한 번에 조회 (N+1 문제 해결)
        placeholders = ",".join(["?" for _ in filenames])
        sql = f"SELECT * FROM documents WHERE filename IN ({placeholders})"
        params = list(filenames)

        if drafter_filter:
            sql += " AND drafter = ?"
            params.append(drafter_filter)

        if year_filter:
            sql += """
                AND (
                    (display_date IS NOT NULL AND display_date LIKE ?)
                    OR (display_date IS NULL AND date IS NOT NULL AND date LIKE ?)
                    OR (display_date IS NULL AND date IS NULL AND year = ?)
                )
            """
            params.extend([f"{year_filter}%", f"{year_filter}%", year_filter])

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

        # 결과를 filename 기준으로 매핑
        row_map = {dict(row)["filename"]: dict(row) for row in rows}

        # 원래 순서 유지하며 결과 구성
        for filename in filenames:
            if filename in row_map:
                doc = row_map[filename]
                doc_details.append({
                    "filename": filename,
                    "drafter": doc.get("drafter", "작성자 미상"),
                    "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                    "doctype": doc.get("doctype", "문서"),
                    "claimed_total": doc.get("claimed_total"),
                    "text_preview": doc.get("text_preview", "")[:HandlerConfig.TEXT_PREVIEW_MAX],
                })
            elif not drafter_filter and not year_filter:
                # 필터가 전혀 없을 때만 메타데이터 없는 문서 포함
                # year_filter가 있으면 필터링된 문서는 버림
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
        """정밀 검색용 문서 상세 정보 조회 (2025-12-21: 배치 쿼리로 최적화)"""
        if not filenames:
            return []

        doc_details = []
        conn = self._db._get_conn()

        # 배치 쿼리로 한 번에 조회 (N+1 문제 해결)
        placeholders = ",".join(["?" for _ in filenames])
        cursor = conn.execute(
            f"SELECT * FROM documents WHERE filename IN ({placeholders})",
            filenames,
        )
        rows = cursor.fetchall()

        # 결과를 filename 기준으로 매핑
        row_map = {dict(row)["filename"]: dict(row) for row in rows}

        # 원래 순서 유지하며 결과 구성
        for filename in filenames:
            if filename in row_map:
                doc = row_map[filename]
                doc_details.append({
                    "filename": filename,
                    "title": doc.get("title", filename),
                    "category": doc.get("category", "기안서"),
                    "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                    "drafter": doc.get("drafter", "작성자 미상"),
                    "claimed_total": doc.get("claimed_total", 0),
                    "text_preview": doc.get("text_preview", "")[:HandlerConfig.TEXT_PREVIEW_SHORT],
                    "path": doc.get("path", ""),
                })

        return doc_details

    def _build_search_response(
        self,
        keywords: str,
        query: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str],
        metadata_only: bool = False,
    ) -> dict[str, Any]:
        """검색 응답 생성

        Args:
            keywords: 검색 키워드
            query: 원본 쿼리
            doc_details: 문서 상세 정보 리스트
            filenames: 전체 파일명 리스트
            metadata_only: True면 메타데이터만 표시 (전문 제외, 성능 최적화)
        """
        # 카드 생성 (2025-12-11: 깔끔한 형식으로 개선)
        # 2025-12-25: "문서 전부" 요청 시 메타데이터만 표시 (성능 최적화)
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
        total_count = len(filenames)  # 전체 검색 결과 수
        display_count = len(doc_details)  # 표시되는 문서 수

        if is_count_query(query):
            answer_text = f"**'{keywords}' 관련 문서는 총 {total_count}개**입니다.\n\n"
            answer_text += "\n\n".join(cards[:HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT])
            if len(cards) > HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT:
                answer_text += f"\n\n... 외 {len(cards) - HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT}개 문서"
        else:
            # 총 건수 vs 표시 건수 구분
            if total_count > display_count:
                answer_text = f"📄 **'{keywords}' 관련 문서 (총 {total_count}건 중 {display_count}건)**\n\n"
            else:
                answer_text = f"📄 **'{keywords}' 관련 문서 ({display_count}건)**\n\n"
            answer_text += "\n\n".join(cards)

            # "문서 전부" 요청이면 성능 최적화 안내 추가
            if metadata_only:
                answer_text += "\n\n💡 **메타데이터 목록만 표시** (빠른 응답)\n"
                answer_text += "상세 내용은 특정 문서명으로 조회하세요."
            # 더 많은 결과가 있으면 힌트 추가
            elif total_count > display_count:
                answer_text += f'\n\n💡 전체 목록: "{keywords} 문서 전부 보여줘"'

        # Evidence 생성
        # "문서 전부" 요청 시 증거는 메타데이터만 (성능 최적화)
        if metadata_only:
            evidence = []  # 전문 검색 없으므로 증거 제외
        else:
            evidence = self._build_evidence(doc_details)

        # 📊 유사 문서 추천 및 병합 (2025-12-08)
        # "문서 전부" 요청 시에는 유사 문서 추천 건너뛰기 (성능 최적화)
        similar_documents = []
        merged_count = 0
        if not metadata_only and filenames and hasattr(self.pipeline, "_similarity_service"):
            try:
                # 전체 출처 문서 제외하고 유사 문서 찾기
                all_similar = self.pipeline._similarity_service.find_similar_by_query(
                    query, filenames, top_k=HandlerConfig.SIMILAR_SEARCH_TOP_K
                )

                # 유사도 임계값 이상은 출처에 병합, 나머지는 유사 문서로 표시
                for sim_doc in all_similar:
                    similarity = sim_doc.get("similarity", 0)
                    if similarity >= HandlerConfig.SIMILAR_MERGE_THRESHOLD:
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

            except (AttributeError, KeyError) as e:
                # 유사도 서비스 접근 오류
                logger.debug(f"⚠️ 유사 문서 추천 실패 (접근 오류, 무시): {e}")

            except Exception as e:
                # 예상치 못한 오류 - 유사 문서 추천은 선택적이므로 무시
                logger.warning(f"⚠️ 유사 문서 추천 실패 ({type(e).__name__}, 무시): {e}")

        return {
            "mode": "SEARCH",
            "text": answer_text,
            "files": filenames,
            "count": len(doc_details),
            "citations": evidence,
            "evidence": evidence,
            "similar_documents": similar_documents[:HandlerConfig.SIMILAR_DISPLAY_LIMIT],  # 📊 유사 문서 추천
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
            "files": filenames[:HandlerConfig.CONTENT_ONLY_RESULT_LIMIT],
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
                    chunks = self.retriever.search(filename, top_k=HandlerConfig.EVIDENCE_CHUNK_TOP_K)
                    if chunks:
                        chunk_text = chunks[0].get("text", "")
                        snippet = chunk_text[:HandlerConfig.EVIDENCE_SNIPPET_MAX] if chunk_text else ""
                except (AttributeError, KeyError) as e:
                    # 검색 결과 구조 오류
                    logger.debug(f"⚠️ BM25 청크 폴백 실패 (구조 오류, {filename}): {e}")

                except Exception as e:
                    # 예상치 못한 오류 - 스니펫 폴백은 선택적이므로 무시
                    logger.debug(f"⚠️ BM25 청크 폴백 실패 ({type(e).__name__}, {filename}): {e}")

            if not snippet:
                snippet = title[:HandlerConfig.TITLE_FALLBACK_MAX]

            evidence.append({
                "doc_id": filename,
                "filename": filename,
                "file_path": file_path,
                "page": 1,
                "snippet": snippet[:HandlerConfig.EVIDENCE_SNIPPET_MAX],
                "ref": None,
                "meta": {
                    "filename": filename,
                    "drafter": doc.get("drafter"),
                    "date": doc.get("date"),
                    "doctype": doc.get("doctype"),
                },
            })

        return evidence
