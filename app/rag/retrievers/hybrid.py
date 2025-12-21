"""하이브리드 검색 엔진 v3.0 (리팩토링 버전)

Stage 기반 아키텍처로 검색 로직을 분리하여 유지보수성 향상.

Stage 순서:
- Stage 0: StrictContentStage (정밀 내용 검색, strict_content=True일 때만)
- Stage 1: ExactMatchStage (모델/부품 코드 정확일치)
- Stage 2: DenseStage (벡터 기반 의미론적 검색)
- Stage 3: MetadataRoutingStage (YEAR + NAME 패턴)
- Stage 4: FTSBM25Stage (FTS + BM25 하이브리드)

2025-12-12 v3.0 변경사항:
- Stage 패턴으로 검색 로직 분리 (SRP)
- RelevanceScorer 클래스로 스코어링 로직 분리
- HybridSearchConfig로 Magic Number 외부화
- 기존 API 완전 호환 유지

2025-12-21 v3.1 변경사항:
- 환경변수 캐싱 (os.getenv 중복 호출 제거)
- SearchQualityLogger 싱글톤 사용
"""

import os
import threading
import traceback
from pathlib import Path
from typing import Any, Optional

import yaml

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.parallel_executor import ParallelSearchExecutor, get_parallel_executor
from app.rag.retrievers.exact_match import ExactMatchRetriever
from app.rag.retrievers.scoring import RelevanceScorer, get_relevance_scorer
from app.rag.retrievers.stages import (
    BaseSearchStage,
    DenseStage,
    ExactMatchStage,
    FTSBM25Stage,
    HybridRanker,
    MetadataRoutingStage,
    SearchContext,
    StageResult,
    StrictContentStage,
    get_hybrid_ranker,
)
from config.constants import HybridRetrieverConfig
from rag_system.active.bm25_store import BM25Store

logger = get_logger(__name__)


# ============================================================================
# 환경변수 캐싱 (모듈 로드 시 1회만 읽음)
# ============================================================================

_ENV_SNIPPET_MAX_LENGTH = int(os.getenv("SNIPPET_MAX_LENGTH", str(HybridRetrieverConfig.SNIPPET_MAX_LENGTH)))
_ENV_RETRIEVE_TOPK = int(os.getenv("RETRIEVE_TOPK", str(HybridRetrieverConfig.RETRIEVE_TOPK)))
_ENV_DISPLAY_LIMIT = int(os.getenv("DISPLAY_LIMIT", str(HybridRetrieverConfig.DISPLAY_LIMIT)))
_ENV_USE_BM25 = os.getenv("RETRIEVER_BACKEND", "bm25").lower() == "bm25"
_ENV_ENABLE_PARALLEL = os.getenv("ENABLE_PARALLEL_SEARCH", "true").lower() == "true"
_ENV_ENABLE_DENSE = os.getenv("ENABLE_DENSE_RETRIEVAL", "true").lower() == "true"
_ENV_ENABLE_EXACT_MATCH = os.getenv("ENABLE_EXACT_MATCH", "true").lower() == "true"
_ENV_BM25_INDEX_PATH = os.getenv("BM25_INDEX_PATH", HybridRetrieverConfig.DEFAULT_BM25_INDEX_PATH)


class ResultsWithStats(list):
    """검색 결과 리스트 + 점수 통계 (duck typing용)

    list를 상속하여 일반 리스트처럼 사용 가능하면서,
    score_stats 속성을 통해 점수 통계 정보도 제공합니다.
    """

    def __init__(self, items: list[dict[str, Any]], stats: dict[str, float]):
        super().__init__(items)
        self.score_stats = stats


class HybridRetriever:
    """하이브리드 검색 엔진 v3.0 (Stage 오케스트레이터)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 Stage 기반 검색 파이프라인을 오케스트레이션합니다.

    Attributes:
        stages: 실행할 검색 Stage 리스트
        scorer: 관련성 스코어링 인스턴스
    """

    def __init__(self) -> None:
        """초기화 - Stage들과 공유 리소스 설정"""
        try:
            # 설정 로드 (캐싱된 환경변수 사용)
            self.snippet_max_length = _ENV_SNIPPET_MAX_LENGTH
            self.retrieve_topk = _ENV_RETRIEVE_TOPK
            self.display_limit = _ENV_DISPLAY_LIMIT
            self.use_bm25 = _ENV_USE_BM25
            self.enable_parallel = _ENV_ENABLE_PARALLEL
            self.enable_dense = _ENV_ENABLE_DENSE

            # 공유 리소스 초기화
            self._init_shared_resources()

            # Stage 파이프라인 구성
            self.stages: list[BaseSearchStage] = self._build_stages()

            # 스코어러 초기화
            self.scorer: RelevanceScorer = get_relevance_scorer()

            # Dense Retrieval Hybrid Ranker
            self.hybrid_ranker: Optional[HybridRanker] = None
            if self.enable_dense:
                self.hybrid_ranker = get_hybrid_ranker()

            # 인덱스 자동 재로드
            self._last_index_mtime = self._get_index_mtime()
            self._reload_lock = threading.RLock()

            logger.info(
                f"✅ HybridRetriever v3.1 초기화 완료 "
                f"({len(self.stages)}개 Stage, "
                f"BM25={self.use_bm25}, "
                f"Dense={self.enable_dense}, "
                f"docs={len(self.bm25.documents) if self.bm25 else 0})"
            )

        except Exception as e:
            logger.error(f"❌ HybridRetriever 초기화 실패: {e}")
            raise

    def _init_shared_resources(self) -> None:
        """공유 리소스 초기화"""
        # MetadataDB
        self.metadata_db = MetadataDB()
        self.known_drafters = self.metadata_db.list_unique_drafters()

        # 병렬 처리
        self.parallel_executor: Optional[ParallelSearchExecutor] = None
        if self.enable_parallel:
            self.parallel_executor = get_parallel_executor(max_workers=HybridRetrieverConfig.PARALLEL_MAX_WORKERS)
            logger.info("✅ Parallel search execution enabled")

        # BM25Store (캐싱된 환경변수 사용)
        self.bm25: Optional[BM25Store] = None
        if self.use_bm25:
            if Path(_ENV_BM25_INDEX_PATH).exists():
                self.bm25 = BM25Store(index_path=_ENV_BM25_INDEX_PATH)
                logger.info(f"✅ BM25Store 로드 완료 ({len(self.bm25.documents)}개 문서)")
            else:
                logger.warning(f"⚠️ BM25 인덱스 없음: {_ENV_BM25_INDEX_PATH}")

        # ExactMatchRetriever (캐싱된 환경변수 사용)
        self.exact_match_enabled = _ENV_ENABLE_EXACT_MATCH
        self.exact_match: Optional[ExactMatchRetriever] = None
        if self.exact_match_enabled:
            self.exact_match = ExactMatchRetriever(db=self.metadata_db)
            logger.info("✅ ExactMatchRetriever 활성화")

        # 라우터 키워드 (DOC_ANCHORED 필터링용)
        self.device_pattern: Optional[str] = None
        self.deny_pattern: Optional[str] = None
        self._load_router_keywords()

    def _build_stages(self) -> list[BaseSearchStage]:
        """검색 Stage 파이프라인 구성"""
        stages = []

        # Stage 0: StrictContentStage
        stages.append(StrictContentStage(
            bm25=self.bm25,
            snippet_max_length=self.snippet_max_length,
        ))

        # Stage 1: ExactMatchStage
        stages.append(ExactMatchStage(
            exact_match_retriever=self.exact_match,
            enabled=self.exact_match_enabled,
        ))

        # Stage 2: DenseStage (벡터 기반 의미론적 검색)
        stages.append(DenseStage(
            enabled=_ENV_ENABLE_DENSE,
            min_score=HybridRetrieverConfig.DENSE_MIN_SCORE,
        ))

        # Stage 3: MetadataRoutingStage
        stages.append(MetadataRoutingStage(
            metadata_db=self.metadata_db,
            retrieve_topk=self.retrieve_topk,
            snippet_max_length=self.snippet_max_length,
        ))

        # Stage 4: FTSBM25Stage
        stages.append(FTSBM25Stage(
            bm25=self.bm25,
            metadata_db=self.metadata_db,
            parallel_executor=self.parallel_executor,
            device_pattern=self.device_pattern,
            snippet_max_length=self.snippet_max_length,
        ))

        # 우선순위 순 정렬
        stages.sort(key=lambda s: s.priority)

        logger.info(f"📋 Stage 파이프라인: {[s.name for s in stages]}")
        return stages

    def _load_router_keywords(self) -> None:
        """라우터 키워드 YAML v2 로드"""
        try:
            config_path = Path(HybridRetrieverConfig.DEFAULT_ROUTER_KEYWORDS_PATH)
            if config_path.exists():
                config = yaml.safe_load(config_path.read_text())

                doc_cfg = config.get("doc_anchored", {})
                profiles = doc_cfg.get("profiles", {})

                if not profiles:
                    raise ValueError("doc_anchored.profiles 섹션이 비어있음")

                all_allow_patterns = []
                all_deny_patterns = []

                for _profile_name, profile_data in profiles.items():
                    allow_list = profile_data.get("allow", [])
                    deny_list = profile_data.get("deny", [])

                    allow_list = [self._expand_macros(p) for p in allow_list]
                    deny_list = [self._expand_macros(p) for p in deny_list]

                    all_allow_patterns.extend(allow_list)
                    all_deny_patterns.extend(deny_list)

                self.device_pattern = "|".join(all_allow_patterns) if all_allow_patterns else None
                self.deny_pattern = "|".join(all_deny_patterns) if all_deny_patterns else None

                logger.info(
                    f"✅ 라우터 키워드 로드 완료: {len(profiles)}개 프로파일, "
                    f"{len(all_allow_patterns)}개 allow 패턴"
                )
            else:
                self._set_fallback_patterns()
                logger.warning("⚠️ router_keywords.yaml 없음, 폴백 패턴 사용")
        except Exception as e:
            logger.error(f"❌ 키워드 로드 실패: {e}, 폴백 패턴 사용")
            self._set_fallback_patterns()

    def _expand_macros(self, pattern: str) -> str:
        """YAML 패턴의 {KBL}/{KBR} 매크로를 정규표현식으로 치환"""
        pattern = pattern.replace("{KBL}", r"(?<![가-힣A-Za-z0-9])")
        pattern = pattern.replace("{KBR}", r"(?![가-힣A-Za-z0-9])")
        return pattern

    def _set_fallback_patterns(self) -> None:
        """폴백 패턴 설정"""
        self.device_pattern = (
            r"\bHRD[-\s]?\d{3,4}\b|DVR|NVR|"
            r"Hanwha(?:\s+(?:Techwin|Vision))?|"
            r"보존용|녹화용|교체|노후|장비|카메라|모니터"
        )
        self.deny_pattern = None

    def _get_index_mtime(self) -> float:
        """인덱스 파일의 수정 시간 반환"""
        if not self.use_bm25:
            return 0.0
        return os.path.getmtime(_ENV_BM25_INDEX_PATH) if Path(_ENV_BM25_INDEX_PATH).exists() else 0.0

    def _reload_if_index_rotated(self) -> None:
        """인덱스 파일이 갱신되면 자동 리로드 (스레드 안전)"""
        if not self.use_bm25:
            return

        current_mtime = self._get_index_mtime()
        if current_mtime > self._last_index_mtime:
            with self._reload_lock:
                # Double-check locking
                current_mtime = self._get_index_mtime()
                if current_mtime > self._last_index_mtime:
                    logger.info("🔄 인덱스 파일 갱신 감지, 재로드 중...")
                    self.bm25 = BM25Store(index_path=_ENV_BM25_INDEX_PATH)
                    self._last_index_mtime = current_mtime

                    # Stage들의 BM25 참조 업데이트
                    for stage in self.stages:
                        if hasattr(stage, "bm25"):
                            stage.bm25 = self.bm25

                    logger.info(f"✅ 인덱스 재로드 완료 ({len(self.bm25.documents)}개 문서)")

    def search(
        self,
        query: str,
        top_k: int,
        mode: str = "chat",
        selected_filename: Optional[str] = None,
        strict_content: bool = False,
    ) -> list[dict[str, Any]]:
        """검색 수행 v3.0

        Stage 파이프라인을 순차 실행하여 검색 결과를 반환합니다.

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            mode: 검색 모드 ("chat", "doc_anchored" 등)
            selected_filename: 선택된 문서 파일명 (우선 검색용)
            strict_content: 정밀 내용 검색 모드

        Returns:
            정규화된 검색 결과 리스트 (ResultsWithStats)
        """
        try:
            # 인덱스 갱신 체크
            self._reload_if_index_rotated()

            # 검색 컨텍스트 생성
            context = SearchContext(
                query=query,
                top_k=top_k,
                mode=mode,
                selected_filename=selected_filename,
                strict_content=strict_content,
            )

            # Stage 파이프라인 실행
            results = self._execute_stages(context)

            # 결과가 비어있으면 빈 결과 반환
            if not results:
                return ResultsWithStats([], self._empty_score_stats())

            # 재스코어링 (strict_content 제외)
            if not strict_content and not selected_filename:
                results = self.scorer.rescore_results(query, results)
                results = self.scorer.apply_filename_similarity_bonus(query, results)
                results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

            # top_k 제한
            results = results[:top_k]

            # 스코어 통계 계산
            score_stats = self._calculate_score_stats(results)

            # 품질 로깅
            self._log_search_quality(query, results, score_stats, mode)

            return ResultsWithStats(results, score_stats)

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            logger.error(traceback.format_exc())
            return ResultsWithStats([], self._empty_score_stats())

    def _execute_stages(self, context: SearchContext) -> list[dict[str, Any]]:
        """Stage 파이프라인 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            검색 결과 리스트
        """
        dense_results = []
        bm25_results = []

        for stage in self.stages:
            # 스킵 조건 체크
            if stage.should_skip(context):
                logger.debug(f"⏭️ {stage.name} 스킵")
                continue

            # Stage 실행
            result: StageResult = stage.execute(context)
            stage._log_execution(context, result)

            # 결과가 있고 조기 종료 조건이면 반환
            if result.results and not result.should_continue:
                logger.info(f"🛑 {stage.name}에서 조기 종료 ({len(result.results)}건)")
                return result.results

            # Dense 결과는 별도 저장 (RRF용)
            if result.results:
                if stage.name == "DenseStage":
                    dense_results = result.results
                else:
                    # BM25/기타 결과 누적
                    bm25_results.extend(result.results)
                    context.add_results(result.results)

        # Dense + BM25 결과가 모두 있으면 RRF 결합
        if dense_results and bm25_results and self.hybrid_ranker:
            logger.info(
                f"🔀 RRF 결합: Dense({len(dense_results)}) + BM25({len(bm25_results)})"
            )
            fused_results = self.hybrid_ranker.fuse(
                bm25_results=bm25_results,
                dense_results=dense_results,
                top_k=context.top_k * HybridRetrieverConfig.RRF_TOPK_MULTIPLIER,
            )
            return fused_results

        # Dense만 있으면 Dense 결과 반환
        if dense_results and not bm25_results:
            return dense_results

        # 누적된 결과 반환 (BM25만 또는 빈 결과)
        return context.accumulated_results

    def _calculate_score_stats(self, results: list[dict[str, Any]]) -> dict[str, float]:
        """스코어 분포 통계 계산"""
        scores = [r.get("score", 0.0) for r in results]
        top1 = scores[0] if len(scores) > 0 else 0.0
        top2 = scores[1] if len(scores) > 1 else 0.0
        top3 = scores[2] if len(scores) > 2 else 0.0

        return {
            "hits": len(results),
            "top1": top1,
            "top2": top2,
            "top3": top3,
            "delta12": max(0.0, top1 - top2),
            "delta13": max(0.0, top1 - top3),
        }

    def _empty_score_stats(self) -> dict[str, float]:
        """빈 스코어 통계"""
        return {
            "hits": 0,
            "top1": 0.0,
            "top2": 0.0,
            "top3": 0.0,
            "delta12": 0.0,
            "delta13": 0.0,
        }

    def _log_search_quality(
        self,
        query: str,
        results: list[dict[str, Any]],
        score_stats: dict[str, float],
        mode: str,
    ) -> None:
        """검색 품질 로깅"""
        backend = "BM25" if (self.use_bm25 and self.bm25) else "MetadataDB"
        logger.info(
            f"🔍 HybridRetriever ({backend}): {len(results)}건 검색 완료 "
            f"(top1={score_stats['top1']:.2f}, delta12={score_stats['delta12']:.2f})"
        )

        try:
            from app.rag.monitoring.search_quality_logger import get_search_quality_logger
            quality_logger = get_search_quality_logger()  # 싱글톤 사용
            quality_logger.log_search(
                query=query,
                results=results,
                score_stats=score_stats,
                metadata={"mode": mode, "backend": backend},
            )
        except Exception as e:
            logger.debug(f"품질 로깅 실패 (무시): {e}")

    def get_metrics(self) -> dict[str, Any]:
        """검색 엔진 메트릭 조회

        Returns:
            메트릭 딕셔너리
        """
        metrics = {
            "retriever_config": {
                "use_bm25": self.use_bm25,
                "exact_match_enabled": self.exact_match_enabled,
                "enable_parallel": self.enable_parallel,
                "retrieve_topk": self.retrieve_topk,
                "display_limit": self.display_limit,
                "snippet_max_length": self.snippet_max_length,
                "stages": [s.name for s in self.stages],
            },
        }

        if self.exact_match_enabled and self.exact_match:
            metrics["exact_match"] = self.exact_match.get_metrics()

        if self.use_bm25 and self.bm25:
            metrics["bm25"] = {
                "total_documents": len(self.bm25.documents),
                "index_path": str(self.bm25.index_path),
            }

        return metrics
