"""
표(비용) 파싱 테스트
2025-10-26
"""

import pytest
from app.rag.parse.parse_tables import TableParser


class TestTableParser:
    """표 파서 테스트"""

    @pytest.fixture
    def parser(self):
        """TableParser 인스턴스 생성"""
        return TableParser()

    def test_number_normalization_basic(self, parser):
        """기본 숫자 정규화 테스트"""
        # 쉼표 제거
        assert parser.normalize_number("1,234,567") == 1234567

        # 원화 기호 제거
        assert parser.normalize_number("1,234,567원") == 1234567

        # 공백 제거
        assert parser.normalize_number("1 234 567") == 1234567

    def test_number_normalization_combined(self, parser):
        """복합 숫자 정규화 테스트"""
        # 모든 특수 문자 포함
        assert parser.normalize_number("₩ 1,234,567 원") == 1234567

    def test_number_normalization_invalid(self, parser):
        """잘못된 숫자 처리 테스트"""
        # 숫자가 아닌 문자열
        assert parser.normalize_number("abc") is None
        assert parser.normalize_number("") is None

    def test_detect_table_headers(self, parser):
        """표 헤더 감지 테스트"""
        text = """
        모델명    수리내역    수량    단가    합계
        ABC-123   점검        2       100,000  200,000원
        """

        headers = parser.detect_table_headers(text)

        # 최소한 몇 개의 헤더가 발견되어야 함
        assert len(headers) > 0
        assert any('모델' in h for h in headers)

    def test_extract_cost_table_basic(self, parser):
        """기본 비용 표 추출 테스트"""
        text = """
        항목별 비용
        항목1: 100,000원
        항목2: 200,000원
        항목3: 300,000원
        합계: 600,000원
        """

        items, success, _ = parser.extract_cost_table(text)

        assert success is True
        assert len(items) >= 3

    def test_validate_sum_match(self, parser):
        """합계 일치 테스트"""
        items = [
            {"name": "항목1", "amount": 100000},
            {"name": "항목2", "amount": 200000},
            {"name": "항목3", "amount": 300000}
        ]

        match, calculated, claimed = parser.validate_sum(items, claimed_total=600000)

        assert match is True
        assert calculated == 600000
        assert claimed == 600000

    def test_validate_sum_mismatch(self, parser):
        """합계 불일치 테스트"""
        items = [
            {"name": "항목1", "amount": 100000},
            {"name": "항목2", "amount": 200000},
            {"name": "항목3", "amount": 300000}
        ]

        # 문서 합계가 틀림
        match, calculated, claimed = parser.validate_sum(items, claimed_total=650000)

        assert match is False
        assert calculated == 600000
        assert claimed == 650000

    def test_validate_sum_tolerance(self, parser):
        """합계 허용 오차 테스트"""
        items = [
            {"name": "항목1", "amount": 100000},
            {"name": "항목2", "amount": 200000},
            {"name": "항목3", "amount": 300000}
        ]

        # ±1원 오차 허용
        match, _, _ = parser.validate_sum(items, claimed_total=600001)

        assert match is True  # 1원 차이는 허용

    def test_extract_claimed_total(self, parser):
        """문서 합계 추출 테스트"""
        text = """
        항목별 비용
        항목1: 100,000원
        항목2: 200,000원
        합계: 300,000원
        """

        claimed_total = parser._extract_claimed_total(text)

        assert claimed_total == 300000

    def test_extract_claimed_total_variants(self, parser):
        """합계 표현 변형 테스트"""
        # "총액" 패턴
        text1 = "총액: 500,000원"
        assert parser._extract_claimed_total(text1) == 500000

        # "소계" 패턴
        text2 = "소계: 300,000원"
        assert parser._extract_claimed_total(text2) == 300000

    def test_parse_full_table(self, parser):
        """전체 표 파싱 테스트"""
        text = """
        수리 내역
        모델명    수량    단가    금액
        A-100     2       100,000  200,000원
        B-200     3       150,000  450,000원
        합계: 650,000원
        """

        result = parser.parse(text)

        # 파싱 성공 확인
        assert result['parse_status'] in ['success', 'partial']

        # 항목 확인
        assert len(result['items']) >= 2

        # 합계 확인
        assert result['total'] > 0

    def test_format_cost_display(self, parser):
        """비용 표시 형식 테스트"""
        parsed_table = {
            'items': [
                {"name": "항목1", "amount": 100000},
                {"name": "항목2", "amount": 200000}
            ],
            'total': 300000,
            'sum_match': True
        }

        display = parser.format_cost_display(parsed_table)

        # Markdown 형식 확인
        assert "💰" in display or "비용" in display
        assert "₩100,000" in display or "100,000" in display
        assert "₩300,000" in display or "300,000" in display

    def test_format_cost_display_mismatch(self, parser):
        """합계 불일치 표시 테스트"""
        parsed_table = {
            'items': [
                {"name": "항목1", "amount": 100000},
                {"name": "항목2", "amount": 200000}
            ],
            'total': 300000,
            'claimed_total': 350000,
            'sum_match': False
        }

        display = parser.format_cost_display(parsed_table)

        # 경고 표시 확인
        assert "⚠" in display or "차이" in display
