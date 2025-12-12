"""StrictContentStage: 정밀 내용 검색 (BM25-only)

QueryExpander/파일명 보너스/메타데이터 라우팅을 비활성화하고
BM25 순수 본문 일치만 반환합니다.
"""

from typing import TYPE_CHECKING, Any, Optional

from app.core.logging import get_logger
from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult

if TYPE_CHECKING:
    from rag_system.active.bm25_store import BM25Store

logger = get_logger(__name__)


# 불용어 목록 (외부화 권장)
STOP_WORDS = frozenset([
    "문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘",
    "내용", "본문", "들어간", "포함", "포함된", "있는", "만", "에", "에서", "이", "가",
])


class StrictContentStage(BaseSearchStage):
    """정밀 내용 검색 Stage (Stage 0)

    strict_content=True일 때만 실행되며,
    BM25 검색 후 실제 content에 키워드가 포함된 것만 필터링합니다.
    """

    name = "StrictContentStage"
    priority = 0

    def __init__(
        self,
        bm25: Optional["BM25Store"] = None,
        snippet_max_length: int = 3600,
    ):
        """초기화

        Args:
            bm25: BM25Store 인스턴스
            snippet_max_length: 스니펫 최대 길이
        """
        self.bm25 = bm25
        self.snippet_max_length = snippet_max_length

    def should_skip(self, context: SearchContext) -> bool:
        """strict_content=False면 스킵"""
        return not context.strict_content

    def execute(self, context: SearchContext) -> StageResult:
        """정밀 내용 검색 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult (should_continue=False로 조기 종료)
        """
        if not self.bm25:
            logger.warning("⚠️ BM25 비활성화 상태에서 STRICT CONTENT 모드 요청됨")
            return self._make_empty_result("BM25 비활성화")

        logger.info("🎯 STRICT CONTENT MODE 활성화: QueryExpander/파일명보너스/메타라우팅 비활성화")

        # BM25-only 검색 (넉넉히 가져옴)
        bm25_results = self.bm25.search(context.query, top_k=context.top_k * 5)

        # 결과를 표준 형식으로 변환
        converted_results = self._convert_results(bm25_results)

        # 핵심 키워드 추출 (불용어 제거)
        core_keyword = self._extract_core_keyword(context.query)
        logger.info(f"🔍 핵심 키워드 추출: '{context.query}' → '{core_keyword}'")

        # 필터링: 실제 content에 키워드가 포함된 것만
        filtered_results = self._filter_by_content(
            converted_results, core_keyword, context.top_k
        )

        logger.info(
            f"✅ STRICT CONTENT 검색 완료: "
            f"{len(bm25_results)}개 → 필터링 {len(filtered_results)}개"
        )

        return StageResult(
            results=filtered_results,
            should_continue=False,  # 조기 종료
            stage_name=self.name,
            metadata={"core_keyword": core_keyword},
        )

    def _convert_results(self, bm25_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """BM25 결과를 표준 형식으로 변환"""
        converted = []
        for result in bm25_results:
            converted.append({
                "doc_id": result.get("filename", "unknown"),
                "snippet": result.get("content", "")[:self.snippet_max_length],
                "score": result.get("score", 0.0),
                "page": 1,
                "filename": result.get("filename"),
                "file_path": result.get("path"),
                "meta": {
                    "filename": result.get("filename"),
                    "date": result.get("date"),
                    "drafter": result.get("drafter"),
                    "category": result.get("category"),
                },
            })
        return converted

    def _extract_core_keyword(self, query: str) -> str:
        """쿼리에서 핵심 키워드 추출 (불용어 제거)"""
        core_keyword = query
        for word in STOP_WORDS:
            core_keyword = core_keyword.replace(word, " ")
        return core_keyword.strip()

    def _filter_by_content(
        self,
        results: list[dict[str, Any]],
        core_keyword: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """content에 키워드가 포함된 결과만 필터링"""
        keyword_variants = core_keyword.split()
        filtered = []

        for doc in results:
            content = doc.get("snippet", "") or ""
            # variant 중 하나라도 content에 포함되면 통과
            for variant in keyword_variants:
                if variant and variant in content:
                    filtered.append(doc)
                    break

            if len(filtered) >= top_k:
                break

        return filtered
