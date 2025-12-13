"""검색 Stage 모듈

각 Stage는 독립적인 검색 전략을 구현하며,
HybridRetriever가 오케스트레이션합니다.

Stage 순서:
- Stage 0: StrictContentStage (정밀 내용 검색)
- Stage 1: ExactMatchStage (모델/부품 코드 정확일치)
- Stage 2: DenseStage (벡터 기반 의미론적 검색) [NEW]
- Stage 3: MetadataRoutingStage (YEAR + NAME 패턴)
- Stage 4: FTSBM25Stage (FTS + BM25 하이브리드)
"""

from app.rag.retrievers.stages.base import BaseSearchStage, SearchContext, StageResult
from app.rag.retrievers.stages.dense import DenseStage, HybridRanker, get_hybrid_ranker
from app.rag.retrievers.stages.exact_match import ExactMatchStage
from app.rag.retrievers.stages.fts_bm25 import FTSBM25Stage
from app.rag.retrievers.stages.metadata_routing import MetadataRoutingStage
from app.rag.retrievers.stages.strict_content import StrictContentStage

__all__ = [
    "BaseSearchStage",
    "DenseStage",
    "ExactMatchStage",
    "FTSBM25Stage",
    "HybridRanker",
    "MetadataRoutingStage",
    "SearchContext",
    "StageResult",
    "StrictContentStage",
    "get_hybrid_ranker",
]
