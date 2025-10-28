#!/usr/bin/env python3
"""
COST_SUM 라우팅 개선 유닛 테스트
2025-10-28

목표:
- 라우팅 정확도 ≥95%
- 회귀 0건 (기존 동작 케이스 유지)
- 실패했던 3개 케이스 수정 검증
"""

import pytest
from app.rag.query_router import QueryRouter, QueryMode


class TestCostSumRouting:
    """COST_SUM 모드 라우팅 테스트"""

    @pytest.fixture
    def router(self):
        """QueryRouter 인스턴스"""
        return QueryRouter()

    # === Regression Tests: 기존 동작 케이스 (0 regressions) ===

    def test_cost_routing_original_얼마였지(self, router):
        """Original Pattern: '얼마였지' 단독 패턴"""
        query = "채널에이 중계차 보수 합계 얼마였지?"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode}"

    def test_cost_routing_original_총액_얼마(self, router):
        """Original Pattern: '총액...얼마' 패턴"""
        query = "2024년 장비 구매 총액 얼마인지 알려줘"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode}"

    def test_cost_routing_original_합계_알려줘(self, router):
        """Original Pattern: '합계...알려줘' 패턴"""
        query = "작년 소모품 합계 알려줘"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode}"

    # === New Pattern Tests: 실패했던 3개 케이스 ===

    def test_cost_routing_fix_총액은(self, router):
        """FIX Case 1: '총액은?' 패턴 (particle + question mark)"""
        query = "최새름이 기안한 문서들의 총액은?"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    def test_cost_routing_fix_비용_합계(self, router):
        """FIX Case 2: '비용 합계' 복합어 패턴 (no verb)"""
        query = "조명 구매 비용 합계"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    def test_cost_routing_fix_소모품_총액(self, router):
        """FIX Case 3: 'context + 총액' 패턴 (no verb)"""
        query = "작년 소모품 구매 총액"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    # === Edge Cases: 추가 검증 ===

    def test_cost_routing_edge_금액은(self, router):
        """Edge Case: '금액은?' 패턴 (다른 비용 키워드 + particle)"""
        query = "남준수가 작성한 문서의 금액은?"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    def test_cost_routing_edge_합계_금액(self, router):
        """Edge Case: '합계 금액' 복합어 패턴"""
        query = "2023년 발주 합계 금액"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    def test_cost_routing_edge_납품_총액(self, router):
        """Edge Case: '납품...총액' context 패턴"""
        query = "부산지국 납품 건 총액"
        mode = router.classify_mode(query)
        assert mode == QueryMode.COST_SUM, f"Expected COST_SUM, got {mode} for '{query}'"

    # === Negative Tests: COST_SUM이 아닌 케이스 ===

    def test_cost_routing_negative_summary(self, router):
        """Negative: 요약 의도가 우선 (SUMMARY로 라우팅)"""
        query = "2024-09-12_조명_소모품_구매_건.pdf 요약해줘"
        mode = router.classify_mode(query)
        assert mode == QueryMode.SUMMARY, f"Expected SUMMARY, got {mode}"

    def test_cost_routing_negative_list(self, router):
        """Negative: 목록 검색 의도 (LIST로 라우팅)"""
        query = "2024년 최새름이 작성한 문서 찾아줘"
        mode = router.classify_mode(query)
        assert mode == QueryMode.LIST, f"Expected LIST, got {mode}"

    def test_cost_routing_negative_qa(self, router):
        """Negative: 일반 질문 (QA로 라우팅)"""
        query = "조명 장비는 어떤 종류가 있나요?"
        mode = router.classify_mode(query)
        assert mode == QueryMode.QA, f"Expected QA, got {mode}"


# === 통합 검증: 전체 정확도 체크 ===

def test_cost_routing_accuracy_batch():
    """전체 COST_SUM 라우팅 정확도 ≥95% 검증"""
    router = QueryRouter()

    # COST_SUM으로 라우팅되어야 하는 케이스
    cost_sum_cases = [
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

    # COST_SUM이 아닌 케이스 (negative cases)
    non_cost_cases = [
        ("2024-09-12_조명_소모품_구매_건.pdf 요약해줘", QueryMode.SUMMARY),
        ("2024년 최새름이 작성한 문서 찾아줘", QueryMode.LIST),
        ("조명 장비는 어떤 종류가 있나요?", QueryMode.QA),
        ("20220111_멀티_스튜디오_PGM_모니터_수리건.pdf", QueryMode.PREVIEW),
    ]

    # COST_SUM 케이스 검증
    cost_correct = 0
    for query in cost_sum_cases:
        mode = router.classify_mode(query)
        if mode == QueryMode.COST_SUM:
            cost_correct += 1
        else:
            print(f"❌ COST_SUM 실패: '{query}' → {mode}")

    # Negative 케이스 검증
    negative_correct = 0
    for query, expected_mode in non_cost_cases:
        mode = router.classify_mode(query)
        if mode == expected_mode:
            negative_correct += 1
        else:
            print(f"❌ Negative 실패: '{query}' → expected {expected_mode}, got {mode}")

    total_cases = len(cost_sum_cases) + len(non_cost_cases)
    total_correct = cost_correct + negative_correct
    accuracy = total_correct / total_cases * 100

    print(f"\n=== COST_SUM 라우팅 정확도 ===")
    print(f"COST_SUM 정확도: {cost_correct}/{len(cost_sum_cases)} ({cost_correct/len(cost_sum_cases)*100:.1f}%)")
    print(f"Negative 정확도: {negative_correct}/{len(non_cost_cases)} ({negative_correct/len(non_cost_cases)*100:.1f}%)")
    print(f"전체 정확도: {total_correct}/{total_cases} ({accuracy:.1f}%)")

    # 정확도 ≥95% 검증
    assert accuracy >= 95.0, f"COST_SUM routing accuracy {accuracy:.1f}% < 95% threshold"
    print(f"\n✅ 목표 달성: {accuracy:.1f}% ≥ 95%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
