"""MetadataRoutingStage: 메타데이터 기반 검색 라우팅 (Stage 2)

YEAR + NAME 패턴이 감지되면 MetadataDB에서 직접 검색합니다.
"""

import re
from typing import TYPE_CHECKING, Any, Optional

from app.core.logging import get_logger
from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult

if TYPE_CHECKING:
    from app.data.metadata_db import MetadataDB

logger = get_logger(__name__)


class MetadataRoutingStage(BaseSearchStage):
    """메타데이터 라우팅 Stage (Stage 2)

    쿼리에서 연도(YEAR)와 이름(NAME)을 추출하여
    MetadataDB에서 직접 검색합니다.
    """

    name = "MetadataRoutingStage"
    priority = 20

    # 패턴 정규표현식
    YEAR_PATTERN = re.compile(r"(\d{4})")
    NAME_PATTERN = re.compile(r"([가-힣]{2,4})")

    def __init__(
        self,
        metadata_db: Optional["MetadataDB"] = None,
        retrieve_topk: int = 200,
        snippet_max_length: int = 3600,
    ):
        """초기화

        Args:
            metadata_db: MetadataDB 인스턴스
            retrieve_topk: 검색 후보 수
            snippet_max_length: 스니펫 최대 길이
        """
        self.metadata_db = metadata_db
        self.retrieve_topk = retrieve_topk
        self.snippet_max_length = snippet_max_length

    def should_skip(self, context: SearchContext) -> bool:
        """strict_content 모드면 스킵"""
        return context.strict_content

    def execute(self, context: SearchContext) -> StageResult:
        """메타데이터 라우팅 검색 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult (결과가 있으면 should_continue=False)
        """
        if not self.metadata_db:
            return self._make_empty_result("MetadataDB 없음")

        # YEAR + NAME 패턴 감지
        year_match = self.YEAR_PATTERN.search(context.query)
        name_match = self.NAME_PATTERN.search(context.query)

        if not (year_match and name_match):
            return self._make_empty_result("YEAR+NAME 패턴 없음")

        year = year_match.group(1)
        name = name_match.group(1)
        logger.info(f"🎯 메타데이터 검색 라우팅: {year}년 + {name}")

        try:
            # MetadataDB에서 직접 검색
            metadata_results = self.metadata_db.search_documents(
                drafter=name,
                year=year,
                limit=self.retrieve_topk,
            )

            if not metadata_results:
                return self._make_empty_result("메타데이터 일치 없음")

            # 결과 변환
            converted_results = self._convert_results(metadata_results)

            # 중복 제거
            deduped_results = self._deduplicate(converted_results)

            logger.info(
                f"📊 메타데이터 검색 결과: {len(metadata_results)}개 → "
                f"중복제거 {len(deduped_results)}개"
            )

            return StageResult(
                results=deduped_results[:context.top_k],
                should_continue=False,  # 조기 종료
                stage_name=self.name,
                metadata={"year": year, "drafter": name},
            )

        except Exception as e:
            logger.error(f"❌ 메타데이터 검색 실패: {e}")
            return self._make_empty_result(f"오류: {e}")

    def _convert_results(
        self, metadata_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """MetadataDB 결과를 표준 형식으로 변환"""
        converted = []
        for result in metadata_results:
            converted.append({
                "doc_id": result.get("filename", "unknown"),
                "snippet": (result.get("text_preview", "") or "")[:self.snippet_max_length],
                "score": 3.0,  # 메타데이터 일치는 높은 점수
                "page": 1,
                "filename": result.get("filename"),
                "file_path": result.get("path"),
                "meta": {
                    "filename": result.get("filename"),
                    "date": result.get("display_date") or result.get("date"),
                    "drafter": result.get("drafter"),
                    "category": result.get("category"),
                    "title": result.get("title", ""),
                },
            })
        return converted

    def _deduplicate(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """파일명 기준 중복 제거"""
        seen = set()
        deduped = []
        for result in results:
            filename = result.get("filename")
            if filename and filename not in seen:
                seen.add(filename)
                deduped.append(result)
        return deduped
