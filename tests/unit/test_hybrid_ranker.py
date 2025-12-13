"""HybridRanker (RRF) 단위 테스트"""

import pytest

from app.rag.retrievers.stages.dense import HybridRanker


class TestHybridRanker:
    """HybridRanker RRF 테스트"""

    def test_init_default(self):
        """기본 초기화"""
        ranker = HybridRanker()
        assert ranker.k == 60
        assert ranker.bm25_weight == 0.5
        assert ranker.dense_weight == 0.5

    def test_init_custom_weights(self):
        """커스텀 가중치"""
        ranker = HybridRanker(bm25_weight=0.7, dense_weight=0.3)
        assert ranker.bm25_weight == 0.7
        assert ranker.dense_weight == 0.3

    def test_fuse_empty_inputs(self):
        """빈 입력"""
        ranker = HybridRanker()
        result = ranker.fuse([], [], top_k=5)
        assert result == []

    def test_fuse_bm25_only(self):
        """BM25 결과만 있을 때"""
        ranker = HybridRanker()
        bm25_results = [
            {"filename": "doc1.pdf", "score": 10.0},
            {"filename": "doc2.pdf", "score": 8.0},
        ]

        result = ranker.fuse(bm25_results, [], top_k=5)

        assert len(result) == 2
        assert result[0]["filename"] == "doc1.pdf"
        assert result[1]["filename"] == "doc2.pdf"

    def test_fuse_dense_only(self):
        """Dense 결과만 있을 때"""
        ranker = HybridRanker()
        dense_results = [
            {"filename": "doc3.pdf", "score": 0.9},
            {"filename": "doc4.pdf", "score": 0.7},
        ]

        result = ranker.fuse([], dense_results, top_k=5)

        assert len(result) == 2
        assert result[0]["filename"] == "doc3.pdf"

    def test_fuse_both_results(self):
        """BM25 + Dense 결합"""
        ranker = HybridRanker(k=60, bm25_weight=0.5, dense_weight=0.5)

        bm25_results = [
            {"filename": "doc1.pdf", "score": 15.0, "snippet": "BM25 result"},
            {"filename": "doc2.pdf", "score": 10.0, "snippet": "BM25 result 2"},
        ]

        dense_results = [
            {"filename": "doc1.pdf", "score": 0.9, "snippet": "Dense result"},
            {"filename": "doc3.pdf", "score": 0.8, "snippet": "Dense only"},
        ]

        result = ranker.fuse(bm25_results, dense_results, top_k=5)

        # doc1이 양쪽에서 1위이므로 최상위
        assert result[0]["filename"] == "doc1.pdf"
        assert result[0]["source"] == "hybrid"
        assert "rrf_score" in result[0]

    def test_fuse_rrf_score_calculation(self):
        """RRF 점수 계산 검증"""
        ranker = HybridRanker(k=60, bm25_weight=0.5, dense_weight=0.5)

        # 동일 문서가 BM25 1위, Dense 1위
        bm25_results = [{"filename": "doc1.pdf", "score": 10.0}]
        dense_results = [{"filename": "doc1.pdf", "score": 0.9}]

        result = ranker.fuse(bm25_results, dense_results, top_k=1)

        # RRF: 0.5/(60+1) + 0.5/(60+1) = 1/(61) ≈ 0.0164
        expected_rrf = 0.5 / 61 + 0.5 / 61
        assert abs(result[0]["rrf_score"] - expected_rrf) < 0.0001

    def test_fuse_top_k_limit(self):
        """top_k 제한"""
        ranker = HybridRanker()

        bm25_results = [
            {"filename": f"doc{i}.pdf", "score": 10 - i}
            for i in range(10)
        ]

        result = ranker.fuse(bm25_results, [], top_k=3)

        assert len(result) == 3

    def test_fuse_preserves_metadata(self):
        """메타데이터 보존"""
        ranker = HybridRanker()

        bm25_results = [
            {
                "filename": "doc1.pdf",
                "score": 10.0,
                "snippet": "test snippet",
                "page": 1,
            }
        ]

        result = ranker.fuse(bm25_results, [], top_k=1)

        assert result[0]["snippet"] == "test snippet"
        assert result[0]["page"] == 1

    def test_fuse_adds_rank_info(self):
        """순위 정보 추가 확인"""
        ranker = HybridRanker()

        bm25_results = [{"filename": "doc1.pdf", "score": 10.0}]
        dense_results = [{"filename": "doc1.pdf", "score": 0.9}]

        result = ranker.fuse(bm25_results, dense_results, top_k=1)

        assert result[0]["bm25_rank"] == 1
        assert result[0]["dense_rank"] == 1
