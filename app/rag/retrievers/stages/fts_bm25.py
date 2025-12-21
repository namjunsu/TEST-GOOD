"""FTSBM25Stage: FTS + BM25 하이브리드 검색 (Stage 3)

FTS 우선 검색, BM25 보충 전략으로 전체 텍스트 기반 검색을 수행합니다.
"""

import re
from typing import TYPE_CHECKING, Any, Optional

from app.core.logging import get_logger
from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult
from config.constants import HybridRetrieverConfig, HybridSearchConfig

if TYPE_CHECKING:
    from app.data.metadata_db import MetadataDB
    from app.rag.parallel_executor import ParallelSearchExecutor
    from app.rag.query_expander import QueryExpander
    from rag_system.active.bm25_store import BM25Store

logger = get_logger(__name__)


class FTSBM25Stage(BaseSearchStage):
    """FTS + BM25 하이브리드 검색 Stage (Stage 3)

    FTS 검색을 우선 수행하고, 결과가 부족하면 BM25로 보충합니다.
    DOC_ANCHORED 모드에서는 장비 관련 키워드로 필터링합니다.
    """

    name = "FTSBM25Stage"
    priority = 30

    def __init__(
        self,
        bm25: Optional["BM25Store"] = None,
        metadata_db: Optional["MetadataDB"] = None,
        query_expander: Optional["QueryExpander"] = None,
        parallel_executor: Optional["ParallelSearchExecutor"] = None,
        device_pattern: Optional[str] = None,
        snippet_max_length: int = HybridRetrieverConfig.SNIPPET_MAX_LENGTH,
    ):
        """초기화

        Args:
            bm25: BM25Store 인스턴스
            metadata_db: MetadataDB 인스턴스
            query_expander: QueryExpander 인스턴스 (Lazy)
            parallel_executor: 병렬 실행기
            device_pattern: DOC_ANCHORED 필터링 패턴
            snippet_max_length: 스니펫 최대 길이
        """
        self.bm25 = bm25
        self.metadata_db = metadata_db
        self._query_expander = query_expander
        self._query_expander_failed = False  # 초기화 실패 플래그
        self.parallel_executor = parallel_executor
        self.device_pattern = device_pattern
        self.snippet_max_length = snippet_max_length

    @property
    def query_expander(self) -> Optional["QueryExpander"]:
        """Query Expander (Lazy initialization)"""
        if self._query_expander is None and not self._query_expander_failed:
            try:
                from app.rag.query_expander import get_query_expander
                self._query_expander = get_query_expander()
                logger.info("✅ Query Expander 초기화 완료 (lazy)")
            except Exception as e:
                logger.warning(f"⚠️ Query Expander 초기화 실패: {e}")
                self._query_expander_failed = True  # 재시도 방지
        return self._query_expander

    def should_skip(self, context: SearchContext) -> bool:
        """strict_content 모드면 스킵"""
        return context.strict_content

    def execute(self, context: SearchContext) -> StageResult:
        """FTS + BM25 하이브리드 검색 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult
        """
        if not self.bm25:
            logger.warning("⚠️ BM25 비활성화, 빈 결과 반환")
            return self._make_empty_result("BM25 비활성화")

        # DOC_ANCHORED 모드: 넉넉하게 검색 후 필터링
        search_k = (
            HybridSearchConfig.DOC_ANCHORED_SEARCH_K
            if context.mode.lower() == "doc_anchored"
            else context.top_k
        )

        # 1. FTS 검색 수행
        fts_results = self._search_fts(context.query, search_k)

        # 2. FTS 결과 충분 여부 판단
        fts_sufficient = len(fts_results) >= search_k * HybridSearchConfig.FTS_SUFFICIENT_RATIO

        if fts_sufficient:
            logger.info(f"✅ FTS 결과 충분 ({len(fts_results)}개), BM25 생략")
            # FTS 결과에 BM25 content 보강
            fts_results = self._enrich_with_bm25_content(fts_results)
            bm25_results = []
            selected_doc = None
        else:
            # FTS 결과 부족, BM25로 보충
            logger.info(f"⚠️ FTS 결과 부족 ({len(fts_results)}개), BM25로 보충")
            bm25_results, selected_doc = self._search_bm25_with_selected(
                context.query, search_k, context.selected_filename
            )

        # 3. FTS + BM25 결과 병합
        merged_results = self._merge_results(fts_results, bm25_results, context)

        # 4. DOC_ANCHORED 필터링
        if context.mode.lower() == "doc_anchored" and self.device_pattern:
            merged_results = self._apply_doc_anchored_filter(
                merged_results, context.top_k
            )

        # 5. 선택된 문서 강제 추가
        if context.selected_filename:
            merged_results = self._ensure_selected_doc(
                merged_results, selected_doc, context
            )

        return StageResult(
            results=merged_results,
            should_continue=True,  # 다음 Stage (후처리) 계속
            stage_name=self.name,
            metadata={
                "fts_count": len(fts_results),
                "bm25_count": len(bm25_results),
                "merged_count": len(merged_results),
            },
        )

    def _search_fts(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """FTS 검색 수행 with Query Expansion"""
        if not self.metadata_db:
            return []

        try:
            conn = self.metadata_db._get_conn()
            expanded_kw_count = 0

            # Query Expansion
            if self.query_expander:
                try:
                    expansion_result = self.query_expander.expand_query(query)
                    fts_query = expansion_result["search_query"]
                    expanded_kw_count = len(expansion_result.get("expanded_keywords", []))
                    logger.info(f"🔍 Query expansion: '{query}' → '{fts_query[:100]}...'")
                except Exception as e:
                    logger.warning(f"⚠️ Query expansion 실패: {e}")
                    fts_query = " OR ".join(f'"{word}"' for word in query.split())
            else:
                fts_query = " OR ".join(f'"{word}"' for word in query.split())

            cursor = conn.execute("""
                SELECT d.filename, d.title, d.drafter, d.date, d.category, d.text_preview, d.path
                FROM documents_fts fts
                JOIN documents d ON fts.rowid = d.rowid
                WHERE documents_fts MATCH ?
                ORDER BY bm25(documents_fts)
                LIMIT ?
            """, (fts_query, top_k * HybridSearchConfig.FTS_OVERSAMPLE_FACTOR))

            results = []
            for row in cursor.fetchall():
                filename, title, drafter, date, category, text_preview, path = row
                results.append({
                    "doc_id": filename,
                    "snippet": text_preview or "",
                    "score": 1.0,  # FTS는 rank만 제공
                    "page": 1,
                    "filename": filename,
                    "file_path": path,
                    "meta": {
                        "filename": filename,
                        "date": date,
                        "drafter": drafter,
                        "category": category,
                    },
                })

            logger.info(
                f"✅ FTS 검색 완료: {len(results)}개 결과 "
                f"(원본='{query}', 확장키워드={expanded_kw_count}개)"
            )
            return results[:top_k]

        except Exception as e:
            logger.error(f"❌ FTS 검색 실패: {e}")
            return []

    def _search_bm25_with_selected(
        self, query: str, top_k: int, selected_filename: Optional[str]
    ) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
        """BM25 검색 (병렬 실행 지원)"""
        if not self.bm25:
            return [], None

        # 병렬 실행
        if self.parallel_executor and selected_filename:
            search_tasks = [
                {
                    "name": "bm25_search",
                    "func": self.bm25.search,
                    "args": (query,),
                    "kwargs": {"top_k": top_k},
                },
                {
                    "name": "selected_doc_lookup",
                    "func": self._find_selected_document,
                    "args": (selected_filename,),
                    "kwargs": {},
                },
            ]
            parallel_results = self.parallel_executor.execute_searches(search_tasks)
            bm25_results = parallel_results.get("bm25_search", [])
            selected_doc = parallel_results.get("selected_doc_lookup")
        else:
            bm25_results = self.bm25.search(query, top_k=top_k)
            selected_doc = None

        return bm25_results, selected_doc

    def _find_selected_document(self, selected_filename: str) -> Optional[dict[str, Any]]:
        """선택된 문서를 MetadataDB에서 검색"""
        if not self.metadata_db:
            return None

        try:
            doc = self.metadata_db.get_by_filename(selected_filename)
            if doc:
                return {
                    "doc_id": doc.get("filename", "unknown"),
                    "snippet": doc.get("text_preview") or "",
                    "score": HybridSearchConfig.SELECTED_DOC_SCORE,
                    "page": 1,
                    "filename": doc.get("filename"),
                    "file_path": doc.get("path"),
                    "meta": {
                        "filename": doc.get("filename"),
                        "date": doc.get("date"),
                        "drafter": doc.get("drafter"),
                        "category": doc.get("category"),
                    },
                }
        except Exception as e:
            logger.error(f"❌ 선택 문서 검색 실패: {e}")
        return None

    def _enrich_with_bm25_content(
        self, fts_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """FTS 결과에 BM25 인덱스의 전체 content 보강"""
        if not fts_results or not self.bm25:
            return fts_results

        try:
            # BM25 인덱스에서 filename → content 매핑 생성
            bm25_content_map = {}
            for idx, content in enumerate(self.bm25.documents):
                if idx < len(self.bm25.metadata):
                    meta = self.bm25.metadata[idx]
                    filename = meta.get("filename") if isinstance(meta, dict) else None
                    if filename and content:
                        bm25_content_map[filename] = content

            # FTS 결과에 content 보강
            enriched_count = 0
            for result in fts_results:
                filename = result.get("filename")
                if filename and filename in bm25_content_map:
                    bm25_content = bm25_content_map[filename]
                    current_snippet = result.get("snippet", "")

                    if len(bm25_content) > len(current_snippet):
                        result["snippet"] = bm25_content[:self.snippet_max_length]
                        result["content"] = bm25_content
                        enriched_count += 1

            if enriched_count > 0:
                logger.info(f"📝 FTS 결과 content 보강: {enriched_count}/{len(fts_results)}개")

            return fts_results

        except Exception as e:
            logger.warning(f"⚠️ FTS content 보강 실패: {e}")
            return fts_results

    def _merge_results(
        self,
        fts_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        context: SearchContext,
    ) -> list[dict[str, Any]]:
        """FTS + BM25 결과 병합 (중복 제거)"""
        merged = []
        seen_filenames = set()

        # 1. FTS 결과 먼저 추가 (우선순위 높음)
        for result in fts_results:
            filename = result.get("filename")
            if filename and filename not in seen_filenames:
                merged.append(result)
                seen_filenames.add(filename)

        # 2. BM25 결과 추가 (FTS에 없는 것만)
        for result in bm25_results:
            filename = result.get("filename")
            if filename and filename not in seen_filenames:
                merged.append({
                    "doc_id": result.get("filename", "unknown"),
                    "snippet": result.get("content", ""),
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
                seen_filenames.add(filename)

        logger.info(
            f"📊 병합 결과: FTS {len(fts_results)}개 + BM25 {len(bm25_results)}개 "
            f"= 총 {len(merged)}개 (중복 제거)"
        )
        return merged

    def _apply_doc_anchored_filter(
        self, results: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        """DOC_ANCHORED 필터링: 장비 관련 키워드만 통과"""
        if not self.device_pattern:
            return results

        filtered = []
        for result in results:
            text = result.get("snippet", "") + " " + result.get("doc_id", "")
            if re.search(self.device_pattern, text, re.IGNORECASE):
                filtered.append(result)

        if not filtered:
            logger.warning("⚠️ DOC_ANCHORED 필터링 결과 없음, 원본 상위 사용")
            return results[:top_k * 3]

        logger.info(f"🎯 DOC_ANCHORED 필터링: {len(results)}개 → {len(filtered)}개")
        return filtered[:top_k]

    def _ensure_selected_doc(
        self,
        results: list[dict[str, Any]],
        selected_doc: Optional[dict[str, Any]],
        context: SearchContext,
    ) -> list[dict[str, Any]]:
        """선택된 문서 최상위 강제 추가"""
        if not context.selected_filename:
            return results

        # 1. 캐시된 selected_doc 사용
        if selected_doc:
            logger.info(f"✅ 병렬/캐시에서 선택 문서 발견: {context.selected_filename}")
        else:
            # 2. 결과에서 찾기
            for result in results:
                if result.get("filename") == context.selected_filename:
                    selected_doc = result.copy()
                    selected_doc["score"] = HybridSearchConfig.SELECTED_DOC_SCORE
                    break

            # 3. MetadataDB에서 직접 검색
            if not selected_doc:
                logger.info(f"🔍 BM25에 없음, MetadataDB에서 직접 검색: {context.selected_filename}")
                selected_doc = self._find_selected_document(context.selected_filename)

        if selected_doc:
            # 기존 결과에서 제거 (중복 방지)
            results = [r for r in results if r.get("filename") != context.selected_filename]
            # 최상위에 강제 추가
            selected_doc_priority = selected_doc.copy()
            selected_doc_priority["score"] = HybridSearchConfig.SELECTED_DOC_SCORE
            results = [selected_doc_priority] + results[:context.top_k - 1]
            logger.info(f"🎯 선택된 문서 최상위 강제 추가: {context.selected_filename}")
        else:
            logger.warning(f"⚠️ 선택된 문서 '{context.selected_filename}'를 찾지 못함")

        return results
