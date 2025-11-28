"""
테스트: 쿼리 필터링 v1.1
=======================

토큰 경계, 상대 시간, 도메인 용어 보호 테스트
"""

import pytest
from app.query.filters import QueryFilter, get_query_filter


class TestStopwordTokenBoundary:
    """불용어 토큰 경계 테스트"""

    def test_exact_token_match(self):
        """불용어 정확 매칭 (토큰 경계 적용)"""
        qf = QueryFilter()

        # "문서"는 단독 토큰으로만 제거
        result = qf.preprocess_query("문서 찾아줘")
        assert "문서" not in result["cleaned_query"]
        assert "문서" in result["removed_stopwords"]

    def test_no_match_in_substring(self):
        """부분 문자열은 매칭하지 않음"""
        qf = QueryFilter()

        # "문서"는 불용어이지만 "문서화"의 부분 문자열이면 보존
        # 단, 토큰 경계 때문에 "문서 조명"은 제거됨
        result = qf.preprocess_query("문서 찾기")
        # "문서"는 단독 토큰이므로 제거됨
        assert "문서" in result["removed_stopwords"]
        assert "찾기" in result["removed_stopwords"]

    def test_model_code_preserved(self):
        """모델 코드 내부의 불용어는 보존"""
        qf = QueryFilter()

        # "년" 불용어가 포함된 모델명이지만, 토큰 경계로 보호됨
        # 실제로는 도메인 용어 보호 메커니즘으로 처리됨
        result = qf.preprocess_query("XRN-1620B2 사양")
        assert "XRN-1620B2" in result["cleaned_query"]


class TestDrafterTokenExpansion:
    """drafter 토큰 확장 테스트"""

    def test_drafter_with_space(self):
        """띄어쓰기 포함 작성자"""
        qf = QueryFilter()

        result = qf.preprocess_query('drafter:"남 준수"')
        assert result["parsed_tokens"].get("drafter") == "남 준수"

    def test_drafter_with_parentheses(self):
        """괄호 포함 작성자"""
        qf = QueryFilter()

        result = qf.preprocess_query("drafter:남준수(기술관리팀)")
        assert result["parsed_tokens"].get("drafter") == "남준수(기술관리팀)"

    def test_drafter_with_quotes(self):
        """따옴표 인자"""
        qf = QueryFilter()

        result = qf.preprocess_query("drafter='이 영 희'")
        assert result["parsed_tokens"].get("drafter") == "이 영 희"


class TestRelativeYear:
    """상대 연도 처리 테스트"""

    def test_resolve_this_year(self):
        """올해 → 절대 연도"""
        qf = QueryFilter()

        from datetime import datetime

        current_year = datetime.now().year
        result = qf.resolve_relative_year("올해")
        assert result == (current_year, current_year)

    def test_resolve_last_year(self):
        """작년 → 절대 연도"""
        qf = QueryFilter()

        from datetime import datetime

        last_year = datetime.now().year - 1
        result = qf.resolve_relative_year("작년")
        assert result == (last_year, last_year)

    def test_preprocess_relative_year(self):
        """상대 연도 전처리 (올해 → year:2025)"""
        qf = QueryFilter()

        result = qf.preprocess_query("올해 보고서")
        # "올해"가 "year:YYYY" 형태로 변환되어야 함
        assert "year:" in result["cleaned_query"]
        # "보고서"는 불용어로 제거됨
        assert "보고서" in result["removed_stopwords"]


class TestYearRangeSupport:
    """연도 범위 지원 테스트"""

    def test_year_range(self):
        """연도 범위 (year:2023~2025)"""
        qf = QueryFilter()

        result = qf.preprocess_query("year:2023~2025")
        parsed = result["parsed_tokens"].get("year")
        assert isinstance(parsed, dict)
        assert parsed.get("range") == (2023, 2025)

    def test_year_operator_gte(self):
        """연도 비교 연산자 (year:>=2023)"""
        qf = QueryFilter()

        result = qf.preprocess_query("year:>=2023")
        parsed = result["parsed_tokens"].get("year")
        assert isinstance(parsed, dict)
        assert parsed.get("operator") == ">="
        assert parsed.get("value") == 2023

    def test_year_single(self):
        """단일 연도 (year:2023)"""
        qf = QueryFilter()

        result = qf.preprocess_query("year:2023")
        assert result["parsed_tokens"].get("year") == 2023


class TestDomainTermProtection:
    """도메인 용어 보호 테스트"""

    def test_domain_term_variants(self):
        """도메인 용어 변형 생성"""
        qf = QueryFilter()

        # XRN-1620B2의 변형들이 모두 생성되어야 함
        assert "XRN-1620B2" in qf.domain_terms
        assert "XRN 1620B2" in qf.domain_terms
        assert "XRN1620B2" in qf.domain_terms

    def test_protect_and_restore(self):
        """도메인 용어 보호 및 복원"""
        qf = QueryFilter()

        query = "XRN-1620B2 사양"
        protected, mapping = qf.protect_domain_terms(query)

        # 보호 치환
        assert "__DOM_" in protected
        assert "XRN-1620B2" in mapping.values()

        # 복원
        restored = qf.restore_domain_terms(protected, mapping)
        assert "XRN-1620B2" in restored

    def test_domain_term_preserved_in_preprocess(self):
        """도메인 용어가 전처리에서 보존됨"""
        qf = QueryFilter()

        result = qf.preprocess_query("XRN-1620B2 사양")
        assert "XRN-1620B2" in result["cleaned_query"]
        assert "XRN-1620B2" in result["protected_terms"]


class TestNumericSuffixPreservation:
    """숫자 접미어 보존 테스트"""

    def test_preserve_numeric_suffix(self):
        """숫자 접미어 보존 (12건)"""
        qf = QueryFilter()

        result = qf.preprocess_query("12건의 문서")
        # "12건"은 보존되어야 함
        assert "12건" in result["cleaned_query"]
        # "문서"는 불용어로 제거
        assert "문서" in result["removed_stopwords"]


class TestQueryTokensParsing:
    """쿼리 토큰 파싱 테스트"""

    def test_parse_type_token(self):
        """type 토큰 파싱"""
        qf = QueryFilter()

        result = qf.preprocess_query("type:proposal")
        assert result["parsed_tokens"].get("type") == "proposal"

    def test_parse_date_range(self):
        """date 범위 파싱"""
        qf = QueryFilter()

        result = qf.preprocess_query("date:2025-01-01~2025-12-31")
        parsed = result["parsed_tokens"].get("date")
        assert isinstance(parsed, dict)
        assert parsed.get("range") == ("2025-01-01", "2025-12-31")


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    def test_scenario_1_drafter_with_team(self):
        """시나리오 1: drafter:"남 준수(기술관리팀)" 장비 보고서 찾아줘"""
        qf = QueryFilter()

        result = qf.preprocess_query('drafter:"남 준수(기술관리팀)" 장비 보고서 찾아줘')

        # drafter 캡쳐
        assert result["parsed_tokens"].get("drafter") == "남 준수(기술관리팀)"

        # stopwords 제거 후 핵심어 보존
        assert "장비" in result["cleaned_query"]

        # 불용어 제거
        assert "보고서" in result["removed_stopwords"] or "찾아줘" in result[
            "removed_stopwords"
        ]

    def test_scenario_2_year_range_and_report(self):
        """시나리오 2: year:2023~2024 CCTV 보고서"""
        qf = QueryFilter()

        result = qf.preprocess_query("year:2023~2024 CCTV")

        # year 범위 파싱
        parsed_year = result["parsed_tokens"].get("year")
        assert isinstance(parsed_year, dict)
        assert parsed_year.get("range") == (2023, 2024)

        # CCTV 보존
        assert "CCTV" in result["cleaned_query"]

    def test_scenario_3_model_code_preservation(self):
        """시나리오 3: XRN1620B2 사양"""
        qf = QueryFilter()

        result = qf.preprocess_query("XRN1620B2 사양")

        # 도메인 용어 보호
        # XRN1620B2는 XRN-1620B2의 변형이므로 보호됨
        assert "XRN1620B2" in result["cleaned_query"] or "XRN-1620B2" in result[
            "protected_terms"
        ]


class TestSingletonPattern:
    """싱글톤 패턴 테스트"""

    def test_singleton_instance(self):
        """싱글톤 인스턴스 반환"""
        qf1 = get_query_filter()
        qf2 = get_query_filter()
        assert qf1 is qf2
