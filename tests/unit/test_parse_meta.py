"""
메타데이터 파싱 테스트
2025-10-26
"""

import pytest
from app.rag.parse.parse_meta import MetaParser


class TestMetaParser:
    """메타데이터 파서 테스트"""

    @pytest.fixture
    def parser(self):
        """MetaParser 인스턴스 생성"""
        return MetaParser()

    def test_date_priority(self, parser):
        """날짜 우선순위 테스트"""
        # config: 시행일자 > 기안일자 > 작성일자
        metadata = {
            '기안일자': '2024-05-14',
            '시행일자': '2024-05-16',
            '작성일자': '2024-05-13'
        }

        display_date, date_detail = parser.parse_dates(metadata)

        assert display_date == '2024-05-16'  # 시행일자가 최우선 (config 반영)
        assert '2024-05-14' in date_detail
        assert '2024-05-16' in date_detail

    def test_date_fallback(self, parser):
        """날짜 폴백 테스트"""
        # 기안일자 없으면 시행일자 사용
        metadata = {
            '시행일자': '2024-05-16',
            '작성일자': '2024-05-13'
        }

        display_date, _ = parser.parse_dates(metadata)

        assert display_date == '2024-05-16'

    def test_date_display_format(self, parser):
        """날짜 표시 형식 테스트"""
        # 기안일자 / 시행일자 형식
        metadata = {
            '기안일자': '2024-05-14',
            '시행일자': '2024-05-16'
        }

        _, date_detail = parser.parse_dates(metadata)

        assert date_detail == '2024-05-14 / 2024-05-16'

    @pytest.mark.skip(reason="카테고리 규칙 미구현 (config에 category_rules 없음, doctype 분류로 대체)")
    def test_category_document_type(self, parser):
        """문서 유형 카테고리 분류 테스트"""
        # "수리" 키워드로 "수리" 카테고리
        category, source = parser.classify_category(
            title="무선 마이크 수리 건",
            content="",
            filename=""
        )

        assert "수리" in category
        assert source == "rule"

    @pytest.mark.skip(reason="카테고리 규칙 미구현 (config에 category_rules 없음, doctype 분류로 대체)")
    def test_category_equipment_type(self, parser):
        """장비 분류 카테고리 테스트"""
        # "무선 마이크" 키워드로 "오디오(무선)" 카테고리
        category, source = parser.classify_category(
            title="무선 마이크 교체",
            content="",
            filename=""
        )

        assert "오디오(무선)" in category or "오디오/무선" in category
        assert source == "rule"

    @pytest.mark.skip(reason="카테고리 규칙 미구현 (config에 category_rules 없음, doctype 분류로 대체)")
    def test_category_combined(self, parser):
        """복합 카테고리 분류 테스트"""
        # 문서 유형 + 장비 분류
        category, source = parser.classify_category(
            title="무선 마이크 수리 건",
            content="중계 장비 점검",
            filename=""
        )

        # 복합 카테고리 (여러 개 조합)
        assert source == "rule"
        assert "/" in category or len(category.split()) > 1  # 복합 카테고리

    def test_category_default(self, parser):
        """기본 카테고리 테스트"""
        # 매칭 안 되면 "미분류"
        category, source = parser.classify_category(
            title="알 수 없는 문서",
            content="",
            filename=""
        )

        assert category == "미분류"
        assert source == "default"

    def test_parse_full_metadata(self, parser):
        """전체 메타데이터 파싱 테스트"""
        metadata = {
            'drafter': '최새름',
            'department': '기술관리팀',
            'doc_number': '2024-001',
            'retention': '3년',
            '기안일자': '2024-05-14',
            '시행일자': '2024-05-16',
            'filename': '2024-05-14_무선_마이크_수리_건.pdf'
        }

        parsed = parser.parse(metadata, title="무선 마이크 수리", content="")

        # 기본 필드 확인
        assert parsed['drafter'] == '최새름'
        assert parsed['department'] == '기술관리팀'
        assert parsed['doc_number'] == '2024-001'
        assert parsed['retention'] == '3년'

        # 날짜 확인
        assert '2024-05-14' in parsed['date_detail']

        # 카테고리 확인 (정보 없음이 아님)
        assert parsed['category'] != '정보 없음'
        assert parsed['category_source'] in ['rule', 'ml', 'default']

    def test_no_info_to_default(self, parser):
        """'정보 없음'을 '미분류'로 변경 테스트"""
        metadata = {}

        parsed = parser.parse(metadata, title="", content="")

        # 카테고리는 "정보 없음"이 아니라 "미분류"
        assert parsed['category'] == '미분류'
