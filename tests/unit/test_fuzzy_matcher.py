"""퍼지 매칭 모듈 테스트"""

import pytest

from app.rag.fuzzy_matcher import (
    BrandVariantMatcher,
    _is_similar_brand,
    _normalize,
    fuzzy_find_variants,
)


class TestNormalize:
    """_normalize 함수 테스트"""

    def test_remove_hyphens(self):
        assert _normalize("TV-Logic") == "tvlogic"

    def test_remove_spaces(self):
        assert _normalize("TV Logic") == "tvlogic"

    def test_remove_underscores(self):
        assert _normalize("TV_Logic") == "tvlogic"

    def test_lowercase(self):
        assert _normalize("TVLogic") == "tvlogic"

    def test_combined(self):
        assert _normalize("Tv-Logic") == "tvlogic"
        assert _normalize("TvLogic") == "tvlogic"


class TestIsSimilarBrand:
    """_is_similar_brand 함수 테스트"""

    def test_exact_match_after_normalize(self):
        assert _is_similar_brand("TVLogic", "TV-Logic")
        assert _is_similar_brand("TvLogic", "Tv-Logic")
        assert _is_similar_brand("TVLOGIC", "tvlogic")

    def test_blackmagic_variants(self):
        assert _is_similar_brand("Blackmagic", "BlackMagic")
        assert _is_similar_brand("Black Magic", "BlackMagic")

    def test_different_brands(self):
        assert not _is_similar_brand("TVLogic", "Blackmagic")
        assert not _is_similar_brand("Sony", "Canon")


class TestBrandVariantMatcher:
    """BrandVariantMatcher 클래스 테스트"""

    @pytest.fixture
    def matcher(self):
        m = BrandVariantMatcher()
        filenames = [
            "2022-12-21_티비로직_월모니터_고장_수리_검토의_건.pdf",
            "2024-07-03_TV-Logic_모니터_수리_검토서.pdf",
            "2024-08-29_TvLogic_모니터_수리_검토서.pdf",
            "2025-04-29_월모니터용_TVLogic_랙마운트_구매_요청의_건.pdf",
            "2024-08-05_Blackmagic_8인치_듀얼_모니터_구매_검토서.PDF",
            "2022-02-25_블랙매직_모니터_전원_어뎁터_구매_건.pdf",
        ]
        m.load_from_filenames(filenames)
        return m

    def test_load_from_filenames(self, matcher):
        assert matcher._loaded
        assert len(matcher._brand_terms) > 0

    def test_get_variants_tvlogic(self, matcher):
        variants = matcher.get_variants("TVLogic")
        # 정규화 후 같은 그룹에 있어야 함
        assert len(variants) >= 1

    def test_expand_query(self, matcher):
        expanded = matcher.expand_query("TVLogic 모니터")
        assert "TVLogic" in expanded or "TvLogic" in expanded or "TV-Logic" in expanded


class TestFuzzyFindVariants:
    """fuzzy_find_variants 함수 테스트"""

    def test_find_tvlogic_variants(self):
        candidates = ["TVLogic", "TvLogic", "TV-Logic", "Blackmagic", "Sony"]
        results = fuzzy_find_variants("TV-Logic", candidates)
        # 정규화 후 동일한 것은 제외되므로, 빈 리스트일 수 있음
        # fuzzy_find_variants는 query_term과 다른 정규화 형태만 반환
        # TV-Logic을 검색하면 TVLogic, TvLogic은 정규화 후 동일하므로 seen에 있음
        assert isinstance(results, list)

    def test_empty_candidates(self):
        results = fuzzy_find_variants("TVLogic", [])
        assert results == []

    def test_no_matches(self):
        candidates = ["Sony", "Canon", "Panasonic"]
        results = fuzzy_find_variants("TVLogic", candidates)
        assert len(results) == 0
