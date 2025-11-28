"""
텍스트 정규화 유틸리티 테스트 (v2.0)
- 쿼리 정규화 (공백/어미/표기 변형)
- 상세모드 감지 (과검출 방지)
- 섹션 앵커 감지 (우선순위)
"""
import pytest

from app.utils.text_normalizer import (
    DETAIL_HIGH_RISK,
    DETAIL_KEYWORDS_BASE,
    SECTION_PATTERNS_PRIORITIZED,
    detect_section,
    is_detailed_mode,
    normalize_query,
)


class TestNormalizeQuery:
    """normalize_query() 테스트"""

    def test_basic_normalization(self):
        """기본 정규화 (소문자 + 공백 압축)"""
        assert normalize_query("HELLO   WORLD") == "hello world"
        assert normalize_query("  multiple   spaces  ") == "multiple spaces"

    def test_korean_variant_normalization(self):
        """한국어 '자세히/상세히' 변형 수렴"""
        # (자|상)세(히|하게)(요|좀)? → (자|상)세히
        assert normalize_query("자세히") == "자세히"
        assert normalize_query("자세하게") == "자세히"
        assert normalize_query("자세히요") == "자세히"
        assert normalize_query("자세히좀") == "자세히"
        assert normalize_query("자세하게요") == "자세히"
        assert normalize_query("자세하게좀") == "자세히"

        assert normalize_query("상세히") == "상세히"
        assert normalize_query("상세하게") == "상세히"
        assert normalize_query("상세히요") == "상세히"
        assert normalize_query("상세하게요") == "상세히"

    def test_fullver_variants(self):
        """영문 'full version' 변형 표준화"""
        # 모든 변형 → "full version"
        assert normalize_query("FullVer") == "full version"
        assert normalize_query("full-ver") == "full version"
        assert normalize_query("full ver") == "full version"
        assert normalize_query("fullversion") == "full version"
        assert normalize_query("full version") == "full version"
        assert normalize_query("FULLVER PLEASE") == "full version please"

    def test_korean_fullver_variants(self):
        """한글 '풀버전' 변형 표준화"""
        # 풀[\s\-]?버(전|젼) → "풀버전"
        assert normalize_query("풀버전") == "풀버전"
        assert normalize_query("풀-버전") == "풀버전"
        assert normalize_query("풀 버전") == "풀버전"
        assert normalize_query("풀버젼") == "풀버전"
        assert normalize_query("풀-버젼") == "풀버전"

    def test_quote_normalization(self):
        """따옴표류 통일"""
        # [\"'""''`´] → "
        assert normalize_query('hello "world"') == 'hello "world"'
        assert normalize_query("hello 'world'") == 'hello "world"'
        assert normalize_query('hello "world"') == 'hello "world"'  # 유니코드 따옴표
        assert normalize_query("hello 'world'") == 'hello "world"'  # 유니코드 따옴표
        assert normalize_query("hello `world`") == 'hello "world"'

    def test_complex_query(self):
        """복합 쿼리 정규화"""
        # "FullVer PLEASE!!" → "full version please!!"
        result = normalize_query("FullVer PLEASE!!")
        assert result == "full version please!!"

        # "풀-버젼 자세하게요" → "풀버전 자세히"
        result = normalize_query("풀-버젼 자세하게요")
        assert result == "풀버전 자세히"

        # "비교 대안  자세히좀" → "비교 대안 자세히"
        result = normalize_query("비교 대안  자세히좀")
        assert result == "비교 대안 자세히"

    def test_empty_input(self):
        """빈 입력 처리"""
        assert normalize_query("") == ""
        assert normalize_query(None) == ""
        assert normalize_query("   ") == ""


class TestIsDetailedMode:
    """is_detailed_mode() 테스트 (과검출 방지)"""

    def test_safe_keywords(self):
        """안전 키워드로 상세모드 트리거"""
        # DETAIL_KEYWORDS_BASE
        assert is_detailed_mode("자세히 알려줘") is True
        assert is_detailed_mode("상세히 설명해줘") is True
        assert is_detailed_mode("구체적으로 보여줘") is True
        assert is_detailed_mode("디테일 좀") is True
        assert is_detailed_mode("세부사항 알려줘") is True
        assert is_detailed_mode("풀버전 보여줘") is True
        assert is_detailed_mode("detail please") is True
        assert is_detailed_mode("full ver") is True
        assert is_detailed_mode("full version") is True

    def test_high_risk_with_context(self):
        """고위험 키워드 + 문맥 동사 → True"""
        # 문맥 패턴: (전부|모두|전체)\s*(보여|알려|출력|정리|표시)
        assert is_detailed_mode("이 문서 전부 보여줘") is True
        assert is_detailed_mode("전체 알려줘") is True
        assert is_detailed_mode("모두 출력해줘") is True
        assert is_detailed_mode("전부 정리해줘") is True
        assert is_detailed_mode("전체 표시해줘") is True

        # 풀로 + 동사
        assert is_detailed_mode("풀로 보여줘") is True
        assert is_detailed_mode("풀로 알려줘") is True

    def test_high_risk_without_context(self):
        """고위험 키워드만 (문맥 동사 없음) → False (과검출 방지)"""
        # 일반 검색 의도로 자주 사용됨
        assert is_detailed_mode("2024년 소모품 검토서 전체 목록") is False
        assert is_detailed_mode("전부 파일 이름") is False  # "전부" 단독
        assert is_detailed_mode("모두 장비 코드") is False
        assert is_detailed_mode("전체 리스트") is False

    def test_extra_keywords(self):
        """추가 키워드 (프로젝트별 확장)"""
        assert is_detailed_mode("요약해줘", extra_keywords=["요약"]) is True
        assert is_detailed_mode("간략히 알려줘", extra_keywords=["간략히"]) is True  # 키워드 추가하면 True
        assert is_detailed_mode("간략히 알려줘", extra_keywords=[]) is False  # 키워드 없으면 False

    def test_normalized_matching(self):
        """정규화 후 매칭 확인"""
        # "FullVer" → "full version" 정규화 후 매칭
        assert is_detailed_mode("FullVer PLEASE") is True
        assert is_detailed_mode("풀-버젼 보여줘") is True
        assert is_detailed_mode("자세하게요 알려줘") is True

    def test_no_trigger(self):
        """트리거 없음 → False"""
        assert is_detailed_mode("일반 검색 쿼리") is False
        assert is_detailed_mode("장비 목록") is False
        assert is_detailed_mode("비용 알려줘") is False


class TestDetectSection:
    """detect_section() 테스트 (우선순위)"""

    def test_korean_sections(self):
        """한국어 섹션 감지"""
        assert detect_section("비교 대안 자세히") == "비교 대안"
        assert detect_section("검토 내용 알려줘") == "검토 내용"
        assert detect_section("예산 정보") == "예산/비용"
        assert detect_section("배경 설명해줘") == "배경/목적"
        assert detect_section("현황 보여줘") == "현황"
        assert detect_section("리스크 분석") == "리스크"
        assert detect_section("일정 알려줘") == "일정/계획"

    def test_english_sections(self):
        """영문 섹션 감지 (국제 문서 대응)"""
        assert detect_section("Show me budget summary") == "예산/비용"
        assert detect_section("What's the background?") == "배경/목적"
        assert detect_section("Current status please") == "현황"
        assert detect_section("Review assessment") == "검토 내용"
        assert detect_section("alternatives and options") == "비교 대안"
        assert detect_section("rationale for selection") == "선정 사유"
        assert detect_section("risk analysis") == "리스크"
        assert detect_section("project timeline") == "일정/계획"

    def test_priority_based_conflict_resolution(self):
        """섹션 충돌 시 우선순위 기반 해결"""
        # 우선순위: 검토 내용 > 예산/비용
        assert detect_section("검토 내용과 비용") == "검토 내용"
        assert detect_section("예산과 검토사항") == "검토 내용"

        # 우선순위: 비교 대안 > 배경/목적
        assert detect_section("대안 배경") == "비교 대안"

        # 우선순위: 선정 사유 > 예산/비용
        assert detect_section("선정 사유와 예산") == "선정 사유"

    def test_normalized_matching(self):
        """정규화 후 매칭 확인"""
        # 공백 압축
        assert detect_section("검토    내용") == "검토 내용"
        assert detect_section("비교  대안") == "비교 대안"

        # 대소문자 무관
        assert detect_section("BUDGET SUMMARY") == "예산/비용"
        assert detect_section("Review Assessment") == "검토 내용"

    def test_no_section(self):
        """섹션 감지 안됨 → None"""
        assert detect_section("일반 검색어") is None
        assert detect_section("장비 목록") is None
        assert detect_section("random text") is None

    def test_korean_english_mixed(self):
        """국영문 혼용"""
        assert detect_section("budget 정보 알려줘") == "예산/비용"
        assert detect_section("검토 review 내용") == "검토 내용"


class TestEdgeCases:
    """경계 케이스"""

    def test_fullver_edge_cases(self):
        """full version 변형 경계 케이스"""
        # 사용자 제안 케이스
        assert normalize_query("풀버젼") == "풀버전"
        assert normalize_query("풀-버젼") == "풀버전"
        assert normalize_query("FullVer") == "full version"

    def test_korean_variant_edge_cases(self):
        """한국어 변형 경계 케이스"""
        # 사용자 제안 케이스
        # "좀요" 조합 처리
        assert normalize_query("자세히좀요...") == "자세히요..."  # "좀"이 제거됨
        assert normalize_query("상세하게좀요") == "상세히요"  # "하게" → "히", "좀" 제거

    def test_context_pattern_edge_cases(self):
        """문맥 패턴 경계 케이스"""
        # 사용자 제안 케이스
        assert is_detailed_mode("예산/비용만 알려줘") is False  # "만"은 동사 아님
        assert is_detailed_mode("예산 전부 알려줘") is True  # "알려" 동사 포함

    def test_multiple_sections(self):
        """여러 섹션 키워드 (우선순위 첫 번째)"""
        # 검토 내용 > 비교 대안 > 선정 사유 > 예산/비용
        assert detect_section("검토내용과 예산과 대안") == "검토 내용"  # "검토내용" 명확히
        assert detect_section("비용과 리스크") == "예산/비용"

    def test_whitespace_normalization(self):
        """공백 정규화 경계 케이스"""
        assert normalize_query("\t\n  hello  \t\n  world  \n") == "hello world"
        assert normalize_query("multiple\t\ttabs") == "multiple tabs"


class TestConstants:
    """상수 검증"""

    def test_detail_keywords_base_present(self):
        """DETAIL_KEYWORDS_BASE 존재 확인"""
        assert isinstance(DETAIL_KEYWORDS_BASE, list)
        assert len(DETAIL_KEYWORDS_BASE) > 0

    def test_detail_high_risk_present(self):
        """DETAIL_HIGH_RISK 존재 확인"""
        assert isinstance(DETAIL_HIGH_RISK, list)
        assert len(DETAIL_HIGH_RISK) > 0

    def test_section_patterns_prioritized(self):
        """SECTION_PATTERNS_PRIORITIZED 우선순위 확인"""
        assert isinstance(SECTION_PATTERNS_PRIORITIZED, list)
        assert len(SECTION_PATTERNS_PRIORITIZED) == 8

        # 우선순위 순서 확인
        sections = [sec for sec, _ in SECTION_PATTERNS_PRIORITIZED]
        assert sections[0] == "검토 내용"  # 가장 높은 우선순위
        assert sections[-1] == "일정/계획"  # 가장 낮은 우선순위

    def test_safe_vs_high_risk_separation(self):
        """안전 키워드와 고위험 키워드 분리 확인"""
        # "전부", "모두", "전체", "풀로"는 DETAIL_KEYWORDS_BASE에서 제외
        for risk_kw in DETAIL_HIGH_RISK:
            assert risk_kw not in DETAIL_KEYWORDS_BASE


class TestRealWorldScenarios:
    """실제 사용 시나리오"""

    def test_broadcast_equipment_query(self):
        """방송 장비 검색 쿼리"""
        # 일반 검색 (상세모드 아님)
        assert is_detailed_mode("LVM-180A 장비 스펙") is False

        # 상세모드 트리거
        assert is_detailed_mode("LVM-180A 장비 스펙 자세히") is True

    def test_budget_section_query(self):
        """예산 섹션 쿼리"""
        assert detect_section("2024년 DVR 구매 예산") == "예산/비용"
        assert detect_section("total cost breakdown") == "예산/비용"

    def test_review_document_query(self):
        """검토서 섹션 쿼리"""
        assert detect_section("기술 검토 내용") == "검토 내용"
        assert detect_section("review assessment summary") == "검토 내용"

    def test_mixed_language_query(self):
        """국영문 혼용 쿼리"""
        # 정규화 확인
        normalized = normalize_query("FullVer 자세하게요 PLEASE")
        assert "full version" in normalized
        assert "자세히" in normalized

        # 상세모드 트리거
        assert is_detailed_mode("FullVer 자세하게요 PLEASE") is True

        # 섹션 감지
        assert detect_section("budget 예산 정보") == "예산/비용"

    def test_vendor_document_query(self):
        """해외 벤더 문서 쿼리"""
        # Blackmagic, AJA 등 영문 문서
        assert detect_section("What are the alternatives?") == "비교 대안"
        assert detect_section("Show me the rationale") == "선정 사유"
        # "risk assessment" → "assessment"가 "검토 내용"에 먼저 매칭됨 (우선순위)
        assert detect_section("risk assessment") == "검토 내용"
        # "risk"만 있는 경우 → "리스크"
        assert detect_section("risk analysis") == "리스크"
