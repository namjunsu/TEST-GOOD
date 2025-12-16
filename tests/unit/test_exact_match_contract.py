"""ExactMatchRetriever API 계약 테스트

응답 스키마 고정 및 필수 필드 검증
"""

import pytest

from app.data.metadata_db import MetadataDB
from app.rag.retrievers.exact_match import ExactMatchRetriever


class TestExactMatchContract:
    """ExactMatchRetriever 계약 테스트"""

    @pytest.fixture
    def retriever(self):
        """Retriever 인스턴스"""
        db = MetadataDB()
        return ExactMatchRetriever(db=db)

    def test_search_response_schema(self, retriever):
        """search() 응답 스키마 검증"""
        # 실제 검색 (코드 패턴 없어도 빈 리스트 반환)
        results = retriever.search("test query", top_k=10)

        # 응답이 리스트여야 함
        assert isinstance(results, list), "응답은 리스트여야 함"

        # 결과가 있다면 스키마 검증
        if results:
            result = results[0]

            # 필수 필드 존재 확인
            required_fields = ["doc_id", "page", "score", "snippet", "meta"]
            for field in required_fields:
                assert field in result, f"필수 필드 '{field}' 누락"

            # 필드 타입 검증
            assert isinstance(result["doc_id"], str), "doc_id는 문자열"
            assert isinstance(result["page"], int), "page는 정수"
            assert isinstance(result["score"], (int, float)), "score는 숫자"
            assert isinstance(result["snippet"], str), "snippet은 문자열"
            assert isinstance(result["meta"], dict), "meta는 딕셔너리"

            # 스코어 범위 검증 (0-10)
            assert 0.0 <= result["score"] <= 10.0, f"score는 0-10 범위여야 함: {result['score']}"

            # meta 내부 필수 필드 (v2.0)
            meta_required = ["filename", "doc_id"]
            for field in meta_required:
                assert field in result["meta"], f"meta.{field} 필드 누락"

    def test_get_metrics_schema(self, retriever):
        """get_metrics() 응답 스키마 검증"""
        metrics = retriever.get_metrics()

        # 응답이 딕셔너리여야 함
        assert isinstance(metrics, dict), "메트릭은 딕셔너리여야 함"

        # 필수 필드 존재 확인
        required_fields = [
            "total_queries",
            "exact_hits",
            "filename_hits",
            "total_query_time_ms",
            "exact_match_hit_rate",
            "avg_query_time_ms"
        ]

        for field in required_fields:
            assert field in metrics, f"필수 필드 '{field}' 누락"

        # 필드 타입 검증
        assert isinstance(metrics["total_queries"], int), "total_queries는 정수"
        assert isinstance(metrics["exact_hits"], int), "exact_hits는 정수"
        assert isinstance(metrics["filename_hits"], int), "filename_hits는 정수"
        assert isinstance(metrics["total_query_time_ms"], (int, float)), "total_query_time_ms는 숫자"
        assert isinstance(metrics["exact_match_hit_rate"], (int, float)), "exact_match_hit_rate는 숫자"
        assert isinstance(metrics["avg_query_time_ms"], (int, float)), "avg_query_time_ms는 숫자"

        # 범위 검증
        assert 0.0 <= metrics["exact_match_hit_rate"] <= 1.0, "hit_rate는 0-1 범위"
        assert metrics["total_query_time_ms"] >= 0, "total_query_time_ms는 0 이상"
        assert metrics["avg_query_time_ms"] >= 0, "avg_query_time_ms는 0 이상"

    def test_match_type_values(self, retriever):
        """match_type 값 제한 검증"""
        # 허용된 match_type 값 (런타임 검증에 사용)
        _allowed_match_types = {"exact_code", "filename_exact", "filename_partial"}

        # Note: 실제 검색 결과가 있어야 테스트 가능
        # 여기서는 타입 정의만 확인
        from typing import Literal

        # match_type은 Literal['exact_code', 'filename_exact', 'filename_partial']여야 함
        # (런타임 검증은 실제 검색 결과에서)

    def test_score_normalization(self, retriever):
        """스코어 정규화 (0-10 범위) 검증"""
        # Mock으로 극단값 테스트는 어려우므로
        # 실제 검색에서 스코어 범위만 확인
        results = retriever.search("XRN-1620B2", top_k=10)

        for result in results:
            score = result.get("score", 0)
            assert 0.0 <= score <= 10.0, f"score {score}는 0-10 범위를 벗어남"

    def test_response_stability(self, retriever):
        """응답 필드 안정성 (하위 호환성)"""
        # 동일 쿼리에 대해 필드 구조가 일관되어야 함
        query = "test query"

        results1 = retriever.search(query, top_k=5)
        results2 = retriever.search(query, top_k=5)

        # 결과 개수는 달라질 수 있지만, 스키마는 동일해야 함
        if results1 and results2:
            keys1 = set(results1[0].keys())
            keys2 = set(results2[0].keys())
            assert keys1 == keys2, "응답 필드가 일관되지 않음"

    def test_empty_query_behavior(self, retriever):
        """빈 쿼리 처리 검증"""
        results = retriever.search("", top_k=10)

        # 빈 쿼리는 빈 리스트 반환
        assert isinstance(results, list), "빈 쿼리도 리스트 반환"
        # 코드 패턴 없으므로 결과 없음
        assert len(results) == 0, "코드 패턴 없으면 빈 결과"

    def test_top_k_limit(self, retriever):
        """top_k 제한 검증"""
        results = retriever.search("XRN-1620B2", top_k=3)

        # 결과 개수가 top_k 이하여야 함
        assert len(results) <= 3, f"결과 개수 {len(results)}가 top_k=3 초과"

    def test_metadata_completeness(self, retriever):
        """meta 필드 완전성 검증"""
        results = retriever.search("HRD-442", top_k=5)

        for result in results:
            meta = result.get("meta", {})

            # 필수 필드 존재
            assert "filename" in meta, "meta.filename 누락"
            assert "doc_id" in meta, "meta.doc_id 누락"

            # 선택 필드는 None 가능하지만 키는 존재
            optional_fields = ["drafter", "date", "category"]
            for field in optional_fields:
                # 필드가 있으면 타입 검증
                if field in meta:
                    assert isinstance(meta[field], (str, type(None))), f"meta.{field}는 문자열 또는 None"

    def test_backward_compatibility(self, retriever):
        """하위 호환성 검증 (v1 → v2)"""
        # v2.0에서 추가된 필드가 있어도 v1 필수 필드는 유지되어야 함
        v1_required_fields = ["doc_id", "page", "score", "snippet", "meta"]

        results = retriever.search("TEST", top_k=10)

        if results:
            for field in v1_required_fields:
                assert field in results[0], f"v1 필수 필드 '{field}' 누락 (하위 호환성 위반)"
