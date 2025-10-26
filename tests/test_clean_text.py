"""
텍스트 노이즈 제거 테스트
2025-10-26
"""

import pytest
from app.rag.preprocess.clean_text import TextCleaner


class TestTextCleaner:
    """텍스트 클리너 테스트"""

    @pytest.fixture
    def cleaner(self):
        """TextCleaner 인스턴스 생성"""
        return TextCleaner()

    def test_remove_timestamp(self, cleaner):
        """타임스탬프 제거 테스트"""
        text = """
문서 제목
프린트 시간: 오후 3:43
본문 내용
인쇄일시: 오전 10:20
"""
        cleaned, counts = cleaner.clean(text)

        # 타임스탬프가 제거되었는지 확인
        assert "오후 3:43" not in cleaned
        assert "오전 10:20" not in cleaned

        # 노이즈 카운트 확인
        assert counts.get('프린트 타임스탬프', 0) >= 2

    def test_remove_url(self, cleaner):
        """URL 제거 테스트"""
        text = """
문서 내용
http://gw.channela-mt.com/approval_form_popup.php?seq=123
더 많은 내용
approval_form_popup.php?id=456
"""
        cleaned, counts = cleaner.clean(text)

        # URL이 제거되었는지 확인
        assert "approval_form_popup.php" not in cleaned

        # 노이즈 카운트 확인 (최소 1개의 URL 패턴이 매칭되어야 함)
        assert counts.get('프린트뷰 URL', 0) >= 1

    def test_remove_page_number(self, cleaner):
        """페이지 번호 제거 테스트"""
        text = """
본문 내용
- 5 -
더 많은 내용
- 10 -
"""
        cleaned, counts = cleaner.clean(text)

        # 페이지 번호가 제거되었는지 확인
        assert "- 5 -" not in cleaned
        assert "- 10 -" not in cleaned

        # 노이즈 카운트 확인
        assert counts.get('페이지 번호', 0) >= 2

    def test_remove_repeated_lines(self, cleaner):
        """반복 라인 제거 테스트"""
        text = """
실제 내용
반복 헤더
반복 헤더
반복 헤더
반복 헤더
다른 내용
"""
        cleaned, counts = cleaner.clean(text)

        # 반복 라인이 제거되었는지 확인 (min_repeat_for_noise=3, 4번 반복 → 모두 제거)
        # 단, deduplicate_lines도 작동하므로 최대 2개까지 남을 수 있음
        assert cleaned.count("반복 헤더") <= 2

        # 노이즈 카운트 확인 (repeated 또는 deduplicated 중 하나)
        total_removed = counts.get('repeated_headers_footers', 0) + counts.get('deduplicated_lines', 0)
        assert total_removed >= 2

    def test_deduplicate_consecutive_lines(self, cleaner):
        """연속 중복 라인 제거 테스트"""
        text = """
내용 1
중복 라인
중복 라인
중복 라인
중복 라인
내용 2
"""
        cleaned, counts = cleaner.clean(text)

        # 연속 중복이 임계값(2)까지만 유지되는지 확인
        assert cleaned.count("중복 라인") <= 2

        # 노이즈 카운트 확인
        assert counts.get('deduplicated_lines', 0) >= 2

    def test_combined_noise_removal(self, cleaner):
        """복합 노이즈 제거 테스트"""
        text = """
문서 제목
오후 3:43 프린트됨
http://gw.channela-mt.com/approval_form_popup.php?seq=123
본문 내용
- 5 -
반복 헤더
반복 헤더
반복 헤더
실제 내용
"""
        cleaned, counts = cleaner.clean(text)

        # 모든 노이즈가 제거되었는지 확인
        assert "오후 3:43" not in cleaned
        assert "approval_form_popup.php" not in cleaned
        assert "- 5 -" not in cleaned

        # 총 노이즈 카운트 확인
        total_removed = sum(counts.values())
        assert total_removed >= 3

    def test_preserve_content(self, cleaner):
        """실제 내용 보존 테스트"""
        text = """
중요한 문서 내용
이것은 유지되어야 합니다
정상적인 문장
"""
        cleaned, _ = cleaner.clean(text)

        # 실제 내용이 유지되는지 확인
        assert "중요한 문서 내용" in cleaned
        assert "이것은 유지되어야 합니다" in cleaned
        assert "정상적인 문장" in cleaned
