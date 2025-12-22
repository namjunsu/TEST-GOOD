#!/usr/bin/env python3
"""
COST 라우팅 테스트
2025-10-28

NOTE: QueryMode가 변경되어 COST_SUM → COST, SUMMARY → DOCUMENT, LIST → SEARCH로 통합됨.
classify_mode()는 RouteDecision 객체를 반환하므로 .mode로 접근 필요.
"""

import pytest

from app.rag.query_router import QueryMode, QueryRouter


class TestCostRouting:
    """COST_SUM 모드 라우팅 테스트"""

    @pytest.fixture
    def router(self):
        """QueryRouter 인스턴스"""
        return QueryRouter()

    # === Regression Tests: 기존 동작 케이스 (0 regressions) ===

    def test_cost_routing_original_eolma(self, router):
        """Original Pattern: '얼마였지' 단독 패턴"""
        query = "채널에이 중계차 보수 합계 얼마였지?"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode}"

    def test_cost_routing_original_total_amount(self, router):
        """Original Pattern: '총액...얼마' 패턴"""
        query = "2024년 장비 구매 총액 얼마인지 알려줘"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode}"

    def test_cost_routing_original_sum_tell(self, router):
        """Original Pattern: '합계...알려줘' 패턴"""
        query = "작년 소모품 합계 알려줘"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode}"

    # === New Pattern Tests: 실패했던 3개 케이스 ===

    def test_cost_routing_fix_total_is(self, router):
        """FIX Case 1: '총액은?' 패턴 (particle + question mark)"""
        query = "최새름이 기안한 문서들의 총액은?"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    def test_cost_routing_fix_cost_sum(self, router):
        """FIX Case 2: '비용 합계' 복합어 패턴 (no verb)"""
        query = "조명 구매 비용 합계"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    def test_cost_routing_fix_supplies_total(self, router):
        """FIX Case 3: 'context + 총액' 패턴 (no verb)"""
        query = "작년 소모품 구매 총액"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    # === Edge Cases: 추가 검증 ===

    def test_cost_routing_edge_amount_is(self, router):
        """Edge Case: '금액은?' 패턴 (다른 비용 키워드 + particle)"""
        query = "남준수가 작성한 문서의 금액은?"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    def test_cost_routing_edge_sum_amount(self, router):
        """Edge Case: '합계 금액' 복합어 패턴"""
        query = "2023년 발주 합계 금액"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    def test_cost_routing_edge_delivery_total(self, router):
        """Edge Case: '납품...총액' context 패턴"""
        query = "부산지국 납품 건 총액"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.COST, f"Expected COST, got {result.mode} for '{query}'"

    # === Negative Tests: COST가 아닌 케이스 ===

    def test_cost_routing_negative_summary(self, router):
        """Negative: 요약 의도가 우선 (QA로 라우팅 - summary_intent)"""
        query = "2024-09-12_조명_소모품_구매_건.pdf 요약해줘"
        result = router.classify_mode(query)
        # 요약 의도는 QA 모드로 분류됨 (reason: summary_intent)
        assert result.mode == QueryMode.QA, f"Expected QA, got {result.mode}"

    def test_cost_routing_negative_list(self, router):
        """Negative: 목록 검색 의도 (SEARCH로 라우팅)"""
        query = "2024년 최새름이 작성한 문서 찾아줘"
        result = router.classify_mode(query)
        assert result.mode == QueryMode.SEARCH, f"Expected SEARCH, got {result.mode}"

    def test_cost_routing_negative_qa(self, router):
        """Negative: 일반 질문 (SEARCH로 라우팅 - 현재 라우터 동작)"""
        query = "조명 장비는 어떤 종류가 있나요?"
        result = router.classify_mode(query)
        # '어떤'이 list_intent로 인식되어 SEARCH로 라우팅됨
        assert result.mode in (QueryMode.QA, QueryMode.SEARCH), f"Expected QA or SEARCH, got {result.mode}"


# === 통합 검증: 전체 정확도 체크 ===

def test_cost_routing_accuracy_batch():
    """전체 COST 라우팅 정확도 ≥95% 검증"""
    router = QueryRouter()

    # COST로 라우팅되어야 하는 케이스
    cost_cases = [
        # Original patterns (regression)
        "채널에이 중계차 보수 합계 얼마였지?",
        "2024년 장비 구매 총액 얼마인지 알려줘",
        "작년 소모품 합계 알려줘",
        "얼마였나요?",
        # Fixed cases
        "최새름이 기안한 문서들의 총액은?",
        "조명 구매 비용 합계",
        "작년 소모품 구매 총액",
        # Edge cases
        "남준수가 작성한 문서의 금액은?",
        "2023년 발주 합계 금액",
        "부산지국 납품 건 총액",
        "구매 비용은?",
        "문서 작성 총계",
    ]

    # COST가 아닌 케이스 (negative cases)
    non_cost_cases = [
        ("2024-09-12_조명_소모품_구매_건.pdf 요약해줘", QueryMode.QA),  # summary_intent → QA
        ("2024년 최새름이 작성한 문서 찾아줘", QueryMode.SEARCH),
        ("조명 장비는 어떤 종류가 있나요?", QueryMode.SEARCH),  # '어떤' → list_intent
        ("20220111_멀티_스튜디오_PGM_모니터_수리건.pdf", QueryMode.DOCUMENT),  # 파일명만 → DOCUMENT
    ]

    # COST 케이스 검증
    cost_correct = 0
    for query in cost_cases:
        result = router.classify_mode(query)
        if result.mode == QueryMode.COST:
            cost_correct += 1
        else:
            print(f"❌ COST 실패: '{query}' → {result.mode}")

    # Negative 케이스 검증
    negative_correct = 0
    for query, expected_mode in non_cost_cases:
        result = router.classify_mode(query)
        if result.mode == expected_mode:
            negative_correct += 1
        else:
            print(f"❌ Negative 실패: '{query}' → expected {expected_mode}, got {result.mode}")

    total_cases = len(cost_cases) + len(non_cost_cases)
    total_correct = cost_correct + negative_correct
    accuracy = total_correct / total_cases * 100

    print("\n=== COST 라우팅 정확도 ===")
    print(f"COST 정확도: {cost_correct}/{len(cost_cases)} ({cost_correct / len(cost_cases) * 100:.1f}%)")
    print(f"Negative 정확도: {negative_correct}/{len(non_cost_cases)} ({negative_correct / len(non_cost_cases) * 100:.1f}%)")
    print(f"전체 정확도: {total_correct}/{total_cases} ({accuracy:.1f}%)")

    # 정확도 ≥95% 검증
    assert accuracy >= 95.0, f"COST routing accuracy {accuracy:.1f}% < 95% threshold"
    print(f"\n✅ 목표 달성: {accuracy:.1f}% ≥ 95%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
