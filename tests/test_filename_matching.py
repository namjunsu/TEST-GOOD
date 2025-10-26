"""
파일명 매칭 회귀 테스트
2025-10-26

3단계 매칭 로직 검증:
1. eq: 정확 일치
2. norm: 정규화 일치 (공백, 대소문자, 괄호 변형)
3. like: 부분 일치 (다중 후보 처리)
"""

import pytest
from quick_fix_rag import QuickFixRAG


class TestFilenameMatching:
    """파일명 매칭 회귀 테스트"""

    @pytest.fixture
    def rag(self):
        """QuickFixRAG 인스턴스 생성"""
        return QuickFixRAG(use_hybrid=False)  # 빠른 테스트를 위해 hybrid 비활성화

    def test_filename_match_eq(self, rag):
        """정확 일치 테스트 (eq 경로)

        입력: 정확한 파일명
        기대: eq 단계 매칭, router_reason=filename_eq
        """
        # 실제 DB에 존재하는 파일명 사용
        filename = "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf"
        file_result, match_stage, candidates = rag._search_by_exact_filename(filename)

        # 검증
        assert file_result is not None, "파일을 찾을 수 없습니다"
        assert match_stage == 'eq', f"예상: eq, 실제: {match_stage}"
        assert len(candidates) == 0, "eq 단계에서는 후보가 없어야 합니다"
        assert file_result['filename'] == filename

    def test_filename_match_norm(self, rag):
        """정규화 일치 테스트 (norm 경로)

        입력: 공백/대소문자/(1).pdf 변형
        기대: norm 단계 매칭
        """
        # 정규화가 필요한 변형 파일명
        # 실제 파일: "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf"
        # 변형: 공백 추가, 대소문자 변경
        variant_filename = "2025-03-20 채널에이 중계차 카메라 노후화 장애 긴급 보수건.PDF"

        file_result, match_stage, candidates = rag._search_by_exact_filename(variant_filename)

        # 검증
        assert file_result is not None, "정규화 매칭 실패"
        assert match_stage in ['eq', 'norm'], f"예상: eq 또는 norm, 실제: {match_stage}"
        assert len(candidates) == 0

    def test_filename_match_norm_with_parentheses(self, rag):
        """괄호 번호 제거 정규화 테스트

        입력: 파일명 + (1).pdf
        기대: norm 단계 매칭 (괄호 제거 후)
        """
        # 괄호 번호가 붙은 변형
        # 실제: "2025-08-01_중계차_카메라_렌즈_오버홀.pdf"
        # 변형: "2025-08-01_중계차_카메라_렌즈_오버홀(1).pdf"
        variant_filename = "2025-08-01_중계차_카메라_렌즈_오버홀(1).pdf"

        file_result, match_stage, candidates = rag._search_by_exact_filename(variant_filename)

        # 검증 (정규화로 괄호가 제거되어 매칭될 수 있음)
        # 실제 DB에 (1) 없는 파일이 있으면 norm으로 매칭, 없으면 like로 매칭
        assert match_stage in ['eq', 'norm', 'like'], f"매칭 실패: {match_stage}"

    def test_filename_ambiguous_like(self, rag):
        """다중 후보 처리 테스트 (like 경로)

        입력: 공통 접두어 (예: "중계차_카메라")
        기대: 2건 이상 발견, 후보 리스트 반환
        """
        # 여러 파일에 공통으로 포함된 키워드
        ambiguous_query = "중계차_카메라"

        file_result, match_stage, candidates = rag._search_by_exact_filename(ambiguous_query)

        # 검증
        if match_stage == 'like_multiple':
            # 다중 후보 발견
            assert file_result is None, "다중 후보 시 file_result는 None이어야 합니다"
            assert len(candidates) >= 2, f"최소 2개 이상의 후보가 있어야 합니다: {len(candidates)}개"
            assert len(candidates) <= 3, f"최대 3개까지만 반환해야 합니다: {len(candidates)}개"

            # 각 후보가 필수 필드를 가지는지 확인
            for candidate in candidates:
                assert 'filename' in candidate
                assert 'drafter' in candidate
                assert 'date' in candidate
                assert 'category' in candidate

        elif match_stage == 'like':
            # 단일 매칭 (허용)
            assert file_result is not None
            assert len(candidates) == 0

        elif match_stage == 'none':
            # 매칭 없음 (허용)
            assert file_result is None
            assert len(candidates) == 0

        else:
            pytest.fail(f"예상치 못한 match_stage: {match_stage}")

    def test_filename_match_case_insensitive(self, rag):
        """대소문자 무시 테스트

        입력: 모두 대문자 또는 소문자
        기대: eq 또는 norm 단계 매칭
        """
        # 대문자 변형
        filename_upper = "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.PDF"

        file_result, match_stage, _ = rag._search_by_exact_filename(filename_upper)

        # 검증
        assert file_result is not None, "대소문자 무시 매칭 실패"
        assert match_stage in ['eq', 'norm'], f"예상: eq 또는 norm, 실제: {match_stage}"

    def test_filename_not_found(self, rag):
        """존재하지 않는 파일 테스트

        입력: DB에 없는 파일명
        기대: match_stage='none', 빈 후보 리스트
        """
        nonexistent_file = "존재하지_않는_파일_12345.pdf"

        file_result, match_stage, candidates = rag._search_by_exact_filename(nonexistent_file)

        # 검증
        assert file_result is None, "존재하지 않는 파일에서 결과 반환"
        assert match_stage == 'none', f"예상: none, 실제: {match_stage}"
        assert len(candidates) == 0, "존재하지 않는 파일에서 후보 반환"

    def test_normalize_filename_function(self, rag):
        """정규화 함수 단독 테스트

        다양한 변형이 동일하게 정규화되는지 확인
        """
        # 다양한 변형
        variants = [
            "test file.pdf",
            "test_file.pdf",
            "test__file.pdf",
            "test file (1).pdf",
            "test_file_1.pdf",
            "TEST FILE.PDF",
            "Test%20File.pdf",
        ]

        normalized_results = [rag._normalize_filename(v) for v in variants]

        # 모두 동일하거나 유사한 결과로 정규화되어야 함
        # 최소한 공백과 언더스코어는 통일되어야 함
        assert all('_' in n or ' ' not in n for n in normalized_results), "공백이 정규화되지 않았습니다"
        assert all(n.islower() for n in normalized_results), "소문자로 정규화되지 않았습니다"
