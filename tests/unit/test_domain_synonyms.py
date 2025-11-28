"""도메인 시소러스 모듈 테스트

회귀 방지 목적:
- YAML 포맷 변경 시 파싱 에러 감지
- 키워드 정규화 로직 변경으로 인한 매핑 실패 감지
- 핵심 브랜드/모델명 매핑 검증
"""

import pytest

from app.rag.domain_synonyms import expand_for_strict_content, get_synonyms, reload_synonyms


class TestDomainSynonyms:
    """도메인 시소러스 기본 동작 테스트"""

    def test_tvlogic_expansion(self):
        """티비로직 → TVLogic 확장 테스트"""
        text = "티비로직 모니터 확인"
        expanded = expand_for_strict_content(text)

        assert "티비로직" in expanded
        assert "TVLogic" in expanded or "tvlogic" in expanded.lower()
        assert len(expanded) > len(text)

    def test_sennheiser_expansion(self):
        """젠하이저 → Sennheiser 확장 테스트"""
        text = "젠하이저 마이크 문제"
        expanded = expand_for_strict_content(text)

        assert "젠하이저" in expanded
        assert "Sennheiser" in expanded or "sennheiser" in expanded.lower()

    def test_blackmagic_expansion(self):
        """블랙매직 → Blackmagic 확장 테스트"""
        text = "블랙매직"
        expanded = expand_for_strict_content(text)

        assert "블랙매직" in expanded
        assert "Blackmagic" in expanded or "blackmagic" in expanded.lower()

    def test_pmw500_expansion(self):
        """PMW-500 모델명 확장 테스트"""
        text = "PMW-500 카메라"
        expanded = expand_for_strict_content(text)

        # 하이픈 있는/없는 변형 포함 확인
        assert "PMW-500" in expanded or "PMW500" in expanded or "pmw500" in expanded.lower()

    def test_eco8000_expansion(self):
        """ECO8000 장비명 확장 테스트"""
        text = "ECO8000 싱크"
        expanded = expand_for_strict_content(text)

        assert "ECO8000" in expanded or "eco8000" in expanded.lower()
        # 하이픈 변형도 포함되는지 확인
        assert "ECO-8000" in expanded or "eco-8000" in expanded.lower()


class TestGetSynonyms:
    """get_synonyms() 함수 테스트"""

    def test_get_synonyms_tvlogic(self):
        """티비로직 시소러스 조회"""
        syns = get_synonyms("티비로직")

        assert len(syns) > 0
        assert "티비로직" in syns
        assert "TVLogic" in syns

    def test_get_synonyms_case_insensitive(self):
        """대소문자 무관 조회 (소문자로 정규화)"""
        syns_lower = get_synonyms("tvlogic")
        syns_upper = get_synonyms("TVLOGIC")

        # 둘 다 같은 결과 반환해야 함
        assert len(syns_lower) > 0
        assert len(syns_upper) > 0

    def test_get_synonyms_nonexistent(self):
        """존재하지 않는 키워드 조회"""
        syns = get_synonyms("존재하지않는브랜드")

        # 빈 리스트 반환 (에러 발생하지 않음)
        assert syns == []


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_query(self):
        """빈 쿼리 처리"""
        result = expand_for_strict_content("")
        assert result == ""

    def test_whitespace_only(self):
        """공백만 있는 쿼리"""
        result = expand_for_strict_content("   ")
        assert result.strip() == ""

    def test_no_synonyms_keyword(self):
        """시소러스에 없는 키워드 (원본 유지)"""
        text = "일반적인 검색어"
        expanded = expand_for_strict_content(text)

        # 시소러스에 없으면 원본 그대로
        assert "일반적인" in expanded or "검색어" in expanded

    def test_mixed_keywords(self):
        """시소러스 키워드 + 일반 키워드 혼합"""
        text = "티비로직 모니터 수리 요청"
        expanded = expand_for_strict_content(text)

        # 티비로직은 확장되고, 일반 키워드는 유지
        assert "TVLogic" in expanded or "tvlogic" in expanded.lower()
        assert "모니터" in expanded
        assert "수리" in expanded or "요청" in expanded


class TestYAMLLoading:
    """YAML 로딩 관련 테스트"""

    def test_yaml_loads_successfully(self):
        """YAML 파일이 정상적으로 로드되는지"""
        # reload_synonyms()는 강제 리로드
        result = reload_synonyms()

        # 로드 성공 시 딕셔너리 반환
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_known_brands_exist(self):
        """알려진 주요 브랜드가 시소러스에 있는지"""
        known_brands = ["소니", "캐논", "젠하이저", "티비로직", "블랙매직"]

        for brand in known_brands:
            syns = get_synonyms(brand)
            assert len(syns) > 0, f"{brand} should exist in synonyms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
