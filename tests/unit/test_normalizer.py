"""
텍스트 정규화 모듈 테스트 (개선사항 검증)
"""
import pytest

from app.textproc.normalizer import (
    BRAND_PREFIXES,
    CODE_DENYLIST,
    expand_query_with_variants,
    extract_codes,
    generate_variants,
    is_code_query,
    normalize_code,
    normalize_filename,
    normalize_text,
)


class TestNormalizeText:
    """기본 텍스트 정규화 테스트"""

    def test_nfkc_normalization(self):
        """NFKC 유니코드 정규화"""
        # Full-width → Half-width
        assert normalize_text("ＡＢＣ１２３") == "ABC123"

    def test_hyphen_variants(self):
        """하이픈 계열 통일"""
        # en-dash, em-dash, minus sign → hyphen
        assert normalize_text("XRN‐1620B2") == "XRN-1620B2"  # en-dash
        assert normalize_text("LVM−180A") == "LVM-180A"  # minus
        assert normalize_text("NR—3516P") == "NR-3516P"  # em-dash

    def test_whitespace_compression(self):
        """공백 압축"""
        assert normalize_text("A    B     C") == "A B C"
        assert normalize_text("  leading  trailing  ") == "leading trailing"


class TestNormalizeCode:
    """코드 정규화 테스트"""

    def test_basic_normalization(self):
        """기본 정규화"""
        assert normalize_code("xrn-1620b2") == "XRN1620B2"
        assert normalize_code("LVM 180A") == "LVM180A"
        assert normalize_code("EX-3") == "EX3"

    def test_hyphen_removal(self):
        """하이픈 제거 (순수 영숫자만)"""
        assert normalize_code("XRN-1620-B2") == "XRN1620B2"
        assert normalize_code("NR/3516P/A") == "NR3516PA"

    def test_special_chars_removal(self):
        """특수문자 제거"""
        assert normalize_code("LVM@180#A") == "LVM180A"
        assert normalize_code("XRN_1620_B2") == "XRN1620B2"


class TestGenerateVariants:
    """코드 변형 생성 테스트 (핵심 개선사항)"""

    def test_hyphen_variants(self):
        """하이픈 변형 (구분자 보존)"""
        variants = generate_variants("XRN-1620B2")
        assert "XRN-1620B2" in variants  # 하이픈 유지
        assert "XRN 1620B2" in variants  # 하이픈 → 공백
        assert "XRN1620B2" in variants  # 무공백

    def test_slash_variants(self):
        """슬래시 변형"""
        variants = generate_variants("LVM/180A")
        assert "LVM/180A" in variants or "LVM-180A" in variants  # 슬래시 → 하이픈 통일
        assert "LVM 180A" in variants  # 슬래시 → 공백
        assert "LVM180A" in variants  # 무공백

    def test_space_variants(self):
        """공백 변형"""
        variants = generate_variants("LVM 180A")
        assert "LVM 180A" in variants  # 공백 유지
        assert "LVM180A" in variants  # 무공백

    def test_no_separator(self):
        """구분자 없는 코드"""
        variants = generate_variants("GS724TV6")
        assert "GS724TV6" in variants
        # 구분자 없으면 변형 없음 (1개 또는 중복 제거 후 1개)
        assert len(variants) >= 1

    def test_mixed_separators(self):
        """혼합 구분자 (하이픈 + 슬래시)"""
        variants = generate_variants("COM/GROUP-WARE")
        # 슬래시 → 하이픈 통일 → 교차 변형
        assert any("-" in v or "/" in v or " " in v for v in variants)
        assert any(v.replace("-", "").replace("/", "").replace(" ", "") == "COMGROUPWARE" for v in variants)


class TestExtractCodes:
    """코드 추출 테스트 (패턴 정밀도)"""

    def test_multi_segment(self):
        """멀티세그먼트 코드 (숫자 요구)"""
        text = "XRN-1620B2와 BE-68 장비"
        codes = extract_codes(text, normalize_result=False)
        assert "XRN-1620B2" in codes
        assert "BE-68" in codes

    def test_product_name_with_space(self):
        """공백 포함 제품명 (숫자 요구)"""
        text = "DeckLink 4K Extreme 12G 장비"
        codes = extract_codes(text, normalize_result=False)
        assert "DeckLink 4K Extreme 12G" in codes

    def test_single_form(self):
        """단일형 (영문+숫자 밀착)"""
        text = "LVM180A와 GS724Tv6"
        codes = extract_codes(text, normalize_result=False)
        assert "LVM180A" in codes
        assert "GS724Tv6" in codes

    def test_brand_prefix(self):
        """브랜드 접두어 패턴 (Whitelist)"""
        text = "KONA5 장비"
        codes = extract_codes(text, normalize_result=False)
        assert "KONA5" in codes

    def test_denylist_filtering(self):
        """Denylist 필터링 (오탐 제거)"""
        text = "EMAIL을 보내세요"
        codes = extract_codes(text, normalize_result=False)
        assert "EMAIL" not in codes

    def test_false_positive_reduction(self):
        """순수 영문 오탐 감소 (숫자 요구)"""
        # INTERRUPTIBLEFOLDBACK 같은 긴 영문은 숫자 없으면 제외
        text = "INTERRUPTIBLEFOLDBACK 기능"
        codes = extract_codes(text, normalize_result=False)
        # 브랜드 접두어가 아니면 제외되어야 함
        assert not any("INTERRUPTIBLEFOLDBACK" in c for c in codes)

    def test_mixed_content(self):
        """복합 텍스트"""
        text = "LVM-180A와 XRN-1620B2 장비를 DeckLink 4K Extreme 12G로 교체"
        codes = extract_codes(text, normalize_result=False)
        assert len(codes) >= 3
        assert any("LVM" in c for c in codes)
        assert any("XRN" in c for c in codes)
        assert any("DeckLink" in c for c in codes)


class TestIsCodeQuery:
    """코드 쿼리 판별 테스트"""

    def test_code_present(self):
        """코드 포함"""
        assert is_code_query("XRN-1620B2 사양서")
        assert is_code_query("LVM180A 매뉴얼")

    def test_no_code(self):
        """코드 없음"""
        assert not is_code_query("일반 검색 쿼리")
        assert not is_code_query("방송 장비 목록")


class TestExpandQueryWithVariants:
    """쿼리 확장 테스트 (원문 유지)"""

    def test_basic_expansion(self):
        """기본 확장 (변형 + 원문)"""
        query = "XRN-1620B2 사양"
        expanded = expand_query_with_variants(query)

        # 변형 포함
        assert "XRN-1620B2" in expanded or "XRN1620B2" in expanded
        # OR 연산자
        assert "OR" in expanded
        # 원문 유지 (제거되지 않음)
        assert "사양" in expanded

    def test_multiple_codes(self):
        """여러 코드"""
        query = "LVM-180A와 XRN-1620B2"
        expanded = expand_query_with_variants(query)

        # 두 코드 모두 변형 포함
        assert "LVM" in expanded
        assert "XRN" in expanded
        # OR 연산자
        assert "OR" in expanded

    def test_no_code(self):
        """코드 없음 (원문 정규화만)"""
        query = "일반 검색어"
        expanded = expand_query_with_variants(query)
        assert expanded == normalize_text(query)

    def test_original_query_preserved(self):
        """원문 보존 확인 (제거 방지)"""
        query = "LVM-180A 매뉴얼"
        expanded = expand_query_with_variants(query)

        # 원문 키워드 "매뉴얼"이 유지되어야 함
        assert "매뉴얼" in expanded or "manual" in expanded.lower()


class TestNormalizeFilename:
    """파일명 정규화 테스트 (가독성 보존)"""

    def test_basic_normalization(self):
        """기본 정규화"""
        assert normalize_filename("LVM‐180A_manual.pdf") == "LVM-180A_MANUAL.pdf"
        assert normalize_filename("xrn-1620b2_spec.pdf") == "XRN-1620B2_SPEC.pdf"

    def test_space_to_underscore(self):
        """공백 → 언더스코어"""
        assert normalize_filename("LVM 180A manual.pdf") == "LVM_180A_MANUAL.pdf"

    def test_separator_deduplication(self):
        """구분자 중복 축약"""
        assert normalize_filename("LVM--180A__manual.pdf") == "LVM-180A_MANUAL.pdf"

    def test_extension_lowercase(self):
        """확장자 소문자"""
        assert normalize_filename("file.PDF") == "FILE.pdf"
        assert normalize_filename("file.TXT") == "FILE.txt"

    def test_no_extension(self):
        """확장자 없음"""
        assert normalize_filename("LVM-180A_MANUAL") == "LVM-180A_MANUAL"

    def test_readability_preserved(self):
        """가독성 보존 (하이픈/언더스코어 유지)"""
        result = normalize_filename("LVM-180A_v2.3_manual.pdf")
        assert "-" in result  # 하이픈 보존
        assert "_" in result  # 언더스코어 보존
        assert result.endswith(".pdf")


class TestBrandWhitelist:
    """브랜드 Whitelist 테스트"""

    def test_whitelist_present(self):
        """Whitelist 존재 확인"""
        assert isinstance(BRAND_PREFIXES, set)
        assert len(BRAND_PREFIXES) > 0

    def test_common_brands(self):
        """주요 브랜드 포함 확인"""
        assert "LVM" in BRAND_PREFIXES
        assert "XRN" in BRAND_PREFIXES
        assert "KONA" in BRAND_PREFIXES
        assert "DECKLINK" in BRAND_PREFIXES


class TestDenylist:
    """Denylist 테스트"""

    def test_denylist_present(self):
        """Denylist 존재 확인"""
        assert isinstance(CODE_DENYLIST, set)
        assert len(CODE_DENYLIST) > 0

    def test_common_words(self):
        """일반 용어 포함 확인"""
        assert "EMAIL" in CODE_DENYLIST
        assert "ONAIR" in CODE_DENYLIST
        assert "OFFAIR" in CODE_DENYLIST


class TestEdgeCases:
    """엣지 케이스"""

    def test_empty_string(self):
        """빈 문자열"""
        assert normalize_text("") == ""
        assert normalize_code("") == ""
        assert generate_variants("") == []
        assert extract_codes("") == []
        assert normalize_filename("") == ""

    def test_special_chars_only(self):
        """특수문자만"""
        assert normalize_code("@#$%^&*()") == ""

    def test_numbers_only(self):
        """숫자만"""
        # 숫자만으로는 코드 패턴 미매칭 (영문 필요)
        codes = extract_codes("1234567890")
        assert len(codes) == 0

    def test_korean_only(self):
        """한글만"""
        assert normalize_code("한글코드") == ""
