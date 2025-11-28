#!/usr/bin/env python3
"""
쿼리 라우팅 자동 테스트
패턴 변경 시 회귀 테스트를 위한 테스트 케이스
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.query_router import QueryRouter, QueryMode
import pytest


class TestQueryRouting:
    """쿼리 라우팅 테스트"""

    @pytest.fixture
    def router(self):
        """라우터 인스턴스 생성"""
        return QueryRouter()

    # ===== COST 모드 테스트 =====
    def test_cost_queries(self, router):
        """비용 질의 패턴 테스트"""
        cost_queries = [
            "총액은?",
            "비용 합계는 얼마야?",
            "금액은 얼마였지?",
            "2024년 총액",
            "최새름 기안한 문서 총액",
            "소모품 구매 비용은?",
        ]

        for query in cost_queries:
            result = router.classify_mode(query)
            assert result.mode == QueryMode.COST, f"'{query}' should be COST, got {result.mode}"

    # ===== SEARCH 모드 테스트 =====
    def test_search_queries(self, router):
        """문서 검색 질의 패턴 테스트"""
        search_queries = [
            "최새름 문서 찾아줘",
            "2024년 문서 보여줘",
            "카메라 관련 문서",
            # "중계차 파일 있어?"는 QA 모드 (존재 확인 질문)
            "렌즈 기안서 검색",
            # 개수 질의
            "최새름 문서 총 몇개야?",
            "최새름 문서 개수",
            "남준수 작성한 문서는 몇 개?",
            "2024년 문서 총 개수",
            # "전부" 키워드
            "최새름 문서 전부 보여줘",
            "모든 문서",
            "전체 문서",
        ]

        for query in search_queries:
            result = router.classify_mode(query)
            assert result.mode == QueryMode.SEARCH, f"'{query}' should be SEARCH, got {result.mode}"

    # ===== DOCUMENT 모드 테스트 =====
    def test_document_queries(self, router):
        """문서 내용/요약 질의 패턴 테스트"""
        document_queries = [
            "이 문서 요약해줘",
            "해당 문서 내용 알려줘",
            "2024-10-24_중계차_카메라.pdf 요약",
            "이 파일 정리해줘",
        ]

        for query in document_queries:
            result = router.classify_mode(query)
            assert result.mode == QueryMode.DOCUMENT, f"'{query}' should be DOCUMENT, got {result.mode}"

    # ===== QA 모드 테스트 =====
    def test_qa_queries(self, router):
        """질답 모드 패턴 테스트"""
        qa_queries = [
            "중계차 카메라는 어떻게 수리하나요?",
            "렌즈 오버홀 절차는?",
            "무선 마이크 교체 방법",
            "조명 소모품 종류가 뭐야?",
        ]

        for query in qa_queries:
            result = router.classify_mode(query)
            assert result.mode == QueryMode.QA, f"'{query}' should be QA, got {result.mode}"

    # ===== 경계 케이스 테스트 =====
    def test_edge_cases(self, router):
        """경계 케이스 및 애매한 질의 테스트"""
        # 빈 문자열
        result = router.classify_mode("")
        assert result.mode == QueryMode.QA  # 기본값

        # 짧은 질의
        result = router.classify_mode("카메라")
        assert result.mode == QueryMode.QA  # 검색 의도 불명확

        # 복합 질의 (비용 + 검색)
        result = router.classify_mode("2024년 최새름 문서 총액")
        # COST가 우선순위 높음
        assert result.mode == QueryMode.COST


def test_all_patterns():
    """모든 패턴 일괄 테스트 (pytest 없이 실행 가능)"""
    router = QueryRouter()

    print("=" * 60)
    print("쿼리 라우팅 패턴 테스트 시작")
    print("=" * 60)

    # 테스트 케이스 정의
    test_cases = [
        ("COST", ["총액은?", "비용 합계는 얼마야?", "2024년 총액"]),
        ("SEARCH", ["최새름 문서 찾아줘", "2024년 문서 보여줘"]),
        ("DOCUMENT", ["이 문서 요약해줘", "해당 문서 내용 알려줘"]),
        ("QA", ["중계차 카메라는 어떻게 수리하나요?"]),
    ]

    total = 0
    passed = 0
    failed = []

    for expected_mode, queries in test_cases:
        for query in queries:
            result = router.classify_mode(query)
            actual_mode = result.mode.value.upper()
            total += 1
            if actual_mode == expected_mode:
                passed += 1
                print(f"✅ '{query}' → {actual_mode}")
            else:
                failed.append((query, expected_mode, actual_mode))
                print(f"❌ '{query}' → {actual_mode} (expected {expected_mode})")

    print("\n" + "=" * 60)
    print(f"결과: {passed}/{total} 통과")

    if failed:
        print("\n실패한 테스트:")
        for query, expected, actual in failed:
            print(f"  - '{query}': expected {expected}, got {actual}")
        return False
    else:
        print("✅ 모든 테스트 통과!")
        return True


if __name__ == "__main__":
    # pytest가 없어도 실행 가능
    import sys
    success = test_all_patterns()
    sys.exit(0 if success else 1)
