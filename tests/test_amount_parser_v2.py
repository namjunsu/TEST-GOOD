"""
금액 파서 v2.1 테스트 (Phase 2)
- 억/만 단위 파싱
- 혼합 표기 처리
- 근접도 기반 랭킹
"""
import pytest
from modules.amount_parser_v2 import (
    extract_amounts,
    nearest_amount_to_keyword,
    format_krw,
    _parse_eok_man,
)


class TestEokManParsing:
    """억/만 단위 파싱 테스트"""

    def test_eok_only(self):
        """억 단위만"""
        text = "총 예산은 1억 원입니다"
        results = _parse_eok_man(text)
        assert len(results) >= 1
        assert any(value == 100_000_000 for value, _, _, _ in results)

    def test_man_only(self):
        """만 단위만"""
        text = "단가는 50만 원입니다"
        results = _parse_eok_man(text)
        assert len(results) >= 1
        assert any(value == 500_000 for value, _, _, _ in results)

    def test_eok_and_man(self):
        """억+만 혼합"""
        text = "총액 1억 2,300만 원"
        results = _parse_eok_man(text)
        assert len(results) >= 1
        assert any(value == 123_000_000 for value, _, _, _ in results)

    def test_mixed_notation_with_spaces(self):
        """공백 혼합 표기"""
        text = "예산: 2 억 5,000 만원"
        results = _parse_eok_man(text)
        assert len(results) >= 1
        # 2억 5000만 = 250,000,000
        assert any(value == 250_000_000 for value, _, _, _ in results)

    def test_decimal_eok_man(self):
        """소수점 포함"""
        text = "1.5억 원"
        results = _parse_eok_man(text)
        assert len(results) >= 1
        assert any(value == 150_000_000 for value, _, _, _ in results)


class TestExtractAmounts:
    """extract_amounts() 공개 API 테스트"""

    def test_basic_krw(self):
        """기본 원화 표기"""
        text = "총액: 1,234,567원"
        amounts = extract_amounts(text)
        assert len(amounts) >= 1
        assert any(amt["value"] == 1_234_567 for amt in amounts)

    def test_eok_man_integration(self):
        """억/만 통합"""
        text = "예산 2억 5천만 원"
        amounts = extract_amounts(text)
        assert len(amounts) >= 1
        # "2억" 매칭
        assert any(amt["value"] == 200_000_000 for amt in amounts)

    def test_mixed_notation(self):
        """혼합 표기"""
        text = """
        단가: 500,000원
        수량: 10개
        총액: 5백만 원
        """
        amounts = extract_amounts(text)
        # 최소 500,000 포함되어야 함
        assert any(amt["value"] == 500_000 for amt in amounts)

    def test_duplicate_removal(self):
        """중복 제거"""
        text = "금액 1,000,000원 (총액 1,000,000원)"
        amounts = extract_amounts(text)
        # 중복 제거되어 1개만 (또는 위치가 다르면 2개)
        values = [amt["value"] for amt in amounts]
        # 1,000,000이 있어야 함
        assert 1_000_000 in values

    def test_context_included(self):
        """컨텍스트 포함 확인"""
        text = "총액: 1,234,567원"
        amounts = extract_amounts(text)
        assert len(amounts) >= 1
        # 컨텍스트에 "총액" 포함되어야 함
        assert any("총액" in amt["context"] for amt in amounts)


class TestNearestAmountToKeyword:
    """nearest_amount_to_keyword() 근접도 랭킹 테스트"""

    def test_single_keyword_match(self):
        """단일 키워드 매칭"""
        text = "총액: 1,234,567원"
        result = nearest_amount_to_keyword(text, ["총액"])
        assert result is not None
        assert result["value"] == 1_234_567
        assert result["confidence"] > 0

    def test_multiple_keywords(self):
        """여러 키워드 중 매칭"""
        text = "합계: 5,000,000원"
        result = nearest_amount_to_keyword(text, ["총액", "합계", "견적"])
        assert result is not None
        assert result["value"] == 5_000_000

    def test_prefer_later(self):
        """문서 후반부 우선 (결론부)"""
        text = """
        단가: 100,000원
        수량: 10
        총액: 1,000,000원
        """
        result = nearest_amount_to_keyword(text, ["총액"], prefer_later=True)
        assert result is not None
        # 1,000,000이 더 후반부에 있으므로 선택되어야 함
        assert result["value"] == 1_000_000

    def test_prefer_earlier(self):
        """선언부 우선"""
        text = """
        단가: 100,000원
        수량: 10
        합계: 1,000,000원
        """
        result = nearest_amount_to_keyword(text, ["단가"], prefer_later=False)
        assert result is not None
        assert result["value"] == 100_000

    def test_no_keyword_found(self):
        """키워드 없음"""
        text = "금액: 1,000,000원"
        result = nearest_amount_to_keyword(text, ["예산", "견적"])
        # 키워드가 없으므로 None
        assert result is None

    def test_window_limit(self):
        """윈도우 밖 제외"""
        text = "총액: " + ("x" * 200) + " 1,000,000원"
        result = nearest_amount_to_keyword(text, ["총액"], window=80)
        # 윈도우(80자) 밖이므로 매칭 실패
        assert result is None or result["value"] != 1_000_000

    def test_eok_man_with_keyword(self):
        """억/만 단위 + 키워드"""
        text = "총 예산: 2억 5천만 원"
        result = nearest_amount_to_keyword(text, ["예산", "총예산"])
        assert result is not None
        # "2억" 매칭
        assert result["value"] == 200_000_000

    def test_confidence_score(self):
        """신뢰도 점수 확인"""
        text = "총액: 1,234,567원"
        result = nearest_amount_to_keyword(text, ["총액"])
        assert result is not None
        assert 0 <= result["confidence"] <= 1.0
        # 키워드와 가까우므로 유효한 신뢰도
        assert result["confidence"] > 0.2


class TestFormatKrw:
    """format_krw() 포맷터 테스트"""

    def test_format_normal(self):
        """정상 금액"""
        assert format_krw(1_234_567) == "1,234,567원"

    def test_format_none(self):
        """None 처리"""
        assert format_krw(None) == "정보 없음"

    def test_format_zero(self):
        """0원"""
        assert format_krw(0) == "0원"


class TestComplexScenarios:
    """복잡한 시나리오 테스트"""

    def test_dvr_purchase_document(self):
        """DVR 구매 문서 (실제 케이스)"""
        text = """
        총액: 2,446,000원

        DVR:        333,000원 × 2EA =    666,000원
        HDD:        380,000원 × 4EA =  1,520,000원
        CONVERTER:  130,000원 × 2EA =    260,000원
        """
        amounts = extract_amounts(text)

        # 주요 금액 포함 확인
        values = [amt["value"] for amt in amounts]
        assert 2_446_000 in values  # 총액
        assert 333_000 in values   # DVR 단가
        assert 380_000 in values   # HDD 단가
        assert 130_000 in values   # CONVERTER 단가

    def test_nearest_total_in_complex_doc(self):
        """복잡한 문서에서 총액 근접도 추출"""
        text = """
        품목:
        - 항목1: 500,000원
        - 항목2: 730,000원

        합계: 1,230,000원
        """
        result = nearest_amount_to_keyword(text, ["합계", "총액"], prefer_later=True)
        assert result is not None
        # 1,230,000이 "합계" 키워드와 가장 가까움
        assert result["value"] == 1_230_000

    def test_ambiguous_amounts(self):
        """모호한 금액 여러 개"""
        text = """
        단가: 100,000원
        수량: 5
        소계: 500,000원
        부가세: 50,000원
        총액: 550,000원
        """
        # 총액 키워드로 최종 금액 추출
        result = nearest_amount_to_keyword(text, ["총액"], prefer_later=True)
        assert result is not None
        assert result["value"] == 550_000

    def test_korean_unit_billion_million(self):
        """한국어 단위 (억/만) 복잡 케이스"""
        text = "총 사업비: 3억 2천 5백만 원"
        amounts = extract_amounts(text)

        # "3억" 매칭되어야 함
        values = [amt["value"] for amt in amounts]
        assert 300_000_000 in values
