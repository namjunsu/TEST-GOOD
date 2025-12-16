"""비용 합계 핸들러 모듈

COST_SUM 모드를 처리하는 핸들러.
pipeline.py의 _answer_cost_sum을 위임받아 처리.

search.py에서 분리됨 (SRP 적용).
"""

import sqlite3
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from config.constants import HandlerConfig

from .base import BaseHandler
from .response import format_title_from_filename

if TYPE_CHECKING:
    from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


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
            search_results = self.retriever.search(query, top_k=HandlerConfig.COST_SEARCH_TOP_K)

            if not search_results:
                logger.warning(f"비용 질의 검색 실패: {query}")
                return self._make_empty_response(0)

            # 2. DB에서 claimed_total 수집
            cost_docs = self._collect_cost_docs(search_results)

            if not cost_docs:
                logger.warning("검색된 문서에 비용 정보 없음")
                return self._make_empty_response(len(search_results))

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

        except (AttributeError, KeyError) as e:
            logger.error(f"❌ 검색 결과 구조 오류: {e}", exc_info=True)
            return self._make_error_response("검색 결과 처리 중 데이터 구조 오류가 발생했습니다.")

        except Exception as e:
            logger.exception(f"❌ 비용 질의 예상치 못한 오류: {type(e).__name__}")
            return self._make_error_response("비용 정보 조회 중 예상치 못한 오류가 발생했습니다.")

    def _collect_cost_docs(
        self, search_results: list[dict[str, Any]]
    ) -> list[tuple[int, dict[str, Any], str]]:
        """검색 결과에서 비용 정보가 있는 문서 수집"""
        cost_docs = []
        for result in search_results:
            filename = result.get("meta", {}).get("filename") or result.get("doc_id", "")
            if not filename:
                continue

            doc = self._db.get_by_filename(filename)
            if doc and doc.get("claimed_total"):
                cost_docs.append((doc["claimed_total"], doc, filename))

        return cost_docs

    def _make_empty_response(self, retrieved_count: int) -> dict[str, Any]:
        """빈 결과 응답 생성"""
        msg = "관련 문서를 찾을 수 없습니다." if retrieved_count == 0 else "검색된 문서에 비용 합계 정보가 없습니다."
        return {
            "mode": self.mode,
            "text": msg,
            "files": [],
            "count": 0,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": retrieved_count,
                "selected_count": 0,
                "found": False,
            },
        }

    def _build_cost_response(
        self,
        cost_docs: list[tuple],
        retrieved_count: int,
    ) -> dict[str, Any]:
        """비용 응답 생성"""
        total_sum = sum(doc[0] for doc in cost_docs)
        evidence = []
        filenames = []

        if len(cost_docs) == 1:
            answer_text, evidence, filenames = self._build_single_doc_response(cost_docs[0])
        else:
            answer_text, evidence, filenames = self._build_multi_doc_response(cost_docs, total_sum)

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
                "found": True,
            },
        }

    def _build_single_doc_response(
        self, cost_doc: tuple
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """단일 문서 비용 응답 생성"""
        claimed_total, doc, filename = cost_doc
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
        date_str = doc.get("display_date") or doc.get("date") or "정보 없음"
        drafter_str = doc.get("drafter") or "정보 없음"
        answer_text += f"출처: {filename} | 날짜: {date_str} | 기안자: {drafter_str}\n"
        answer_text += f"검증: {verification}"

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
                "claimed_total": claimed_total,
            },
        }]

        logger.info(f"💰 비용 질의 성공 (단일): {filename} → ₩{claimed_total:,}")
        return answer_text, evidence, [filename]

    def _build_multi_doc_response(
        self, cost_docs: list[tuple], total_sum: int
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """복수 문서 비용 응답 생성"""
        answer_text = f"💰 **총 {len(cost_docs)}건 문서 비용 합계: ₩{total_sum:,}**\n\n"
        answer_text += "**상세 내역:**\n"

        evidence = []
        filenames = []

        for i, (claimed_total, doc, filename) in enumerate(cost_docs[:HandlerConfig.MAX_COST_DOCS_DISPLAY], 1):
            title = format_title_from_filename(filename)

            date_str = doc.get("display_date") or doc.get("date") or "날짜 없음"
            drafter_str = doc.get("drafter") or "정보 없음"
            answer_text += f"{i}. {title}: ₩{claimed_total:,}\n"
            answer_text += f"   📅 {date_str} | 👤 {drafter_str}\n"

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
                    "claimed_total": claimed_total,
                },
            })

        if len(cost_docs) > HandlerConfig.MAX_COST_DOCS_DISPLAY:
            answer_text += f"\n... 외 {len(cost_docs) - HandlerConfig.MAX_COST_DOCS_DISPLAY}건 (합계에 포함)"

        logger.info(f"💰 비용 질의 성공 (복수): {len(cost_docs)}건 → 총 ₩{total_sum:,}")
        return answer_text, evidence, filenames
