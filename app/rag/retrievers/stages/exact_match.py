"""ExactMatchStage: 모델/부품 코드 정확일치 검색 (Stage 1)

ExactMatchRetriever를 래핑하여 Stage 인터페이스로 제공합니다.
"""

from typing import TYPE_CHECKING, Optional

from app.core.logging import get_logger
from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult

if TYPE_CHECKING:
    from app.rag.retrievers.exact_match import ExactMatchRetriever

logger = get_logger(__name__)


class ExactMatchStage(BaseSearchStage):
    """정확일치 검색 Stage (Stage 1)

    모델/부품 코드가 포함된 쿼리에서 정확일치 검색을 수행합니다.
    결과가 있으면 조기 종료합니다.
    """

    name = "ExactMatchStage"
    priority = 10

    def __init__(
        self,
        exact_match_retriever: Optional["ExactMatchRetriever"] = None,
        enabled: bool = True,
    ):
        """초기화

        Args:
            exact_match_retriever: ExactMatchRetriever 인스턴스
            enabled: Stage 활성화 여부
        """
        self.exact_match = exact_match_retriever
        self.enabled = enabled

    def should_skip(self, context: SearchContext) -> bool:
        """ExactMatch 비활성화 또는 strict_content 모드면 스킵"""
        if context.strict_content:
            return True
        if not self.enabled or not self.exact_match:
            return True
        return False

    def execute(self, context: SearchContext) -> StageResult:
        """정확일치 검색 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult (결과가 있으면 should_continue=False)
        """
        if not self.exact_match:
            return self._make_empty_result("ExactMatchRetriever 없음")

        try:
            exact_results = self.exact_match.search(context.query, top_k=context.top_k)

            if exact_results:
                logger.info(
                    f"🎯 Stage 1 (ExactMatch): {len(exact_results)}건 반환, "
                    "하위 Stage 스킵"
                )
                return StageResult(
                    results=exact_results[:context.top_k],
                    should_continue=False,  # 조기 종료
                    stage_name=self.name,
                    metadata={"match_types": self._get_match_types(exact_results)},
                )

            return self._make_empty_result("코드 패턴 없음")

        except Exception as e:
            logger.error(f"❌ ExactMatch 검색 실패: {e}")
            return self._make_empty_result(f"오류: {e}")

    def _get_match_types(self, results: list) -> dict:
        """결과의 match_type 분포 집계"""
        types = {}
        for r in results:
            mt = r.get("match_type", "unknown")
            types[mt] = types.get(mt, 0) + 1
        return types
