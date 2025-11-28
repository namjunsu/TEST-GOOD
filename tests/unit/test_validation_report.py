"""
검증 리포트 테스트 (Phase 3)
- __validation__ 섹션 확인
- 교정/삭제/유지 액션 추적
- confidence 점수 산출
"""
import pytest
from app.rag.utils.json_utils import validate_numeric_fields


class TestValidationReport:
    """__validation__ 섹션 테스트"""

    def test_validation_section_exists(self):
        """__validation__ 섹션 존재 확인"""
        json_data = {
            "details": {"금액": 1_000_000}
        }
        source_text = "금액: 1,000,000원"

        result = validate_numeric_fields(json_data, source_text)

        assert "__validation__" in result
        assert "source_amounts" in result["__validation__"]
        assert "actions" in result["__validation__"]
        assert "confidence" in result["__validation__"]

    def test_source_amounts_populated(self):
        """원문 금액 목록 확인"""
        json_data = {}
        source_text = "단가: 100,000원, 수량: 5, 총액: 500,000원"

        result = validate_numeric_fields(json_data, source_text)

        source_amounts = result["__validation__"]["source_amounts"]
        assert 100_000 in source_amounts
        assert 500_000 in source_amounts


class TestKeepAction:
    """유지 액션 테스트"""

    def test_keep_exact_match(self):
        """정확히 일치하는 금액 유지"""
        json_data = {
            "비용상세": {"총액": 1_234_567}
        }
        source_text = "총액: 1,234,567원"

        result = validate_numeric_fields(json_data, source_text)

        actions = result["__validation__"]["actions"]
        assert len(actions) >= 1
        keep_action = next((a for a in actions if a["action"] == "keep"), None)
        assert keep_action is not None
        assert keep_action["field"] == "비용상세.총액"
        assert keep_action["value"] == 1_234_567
        assert keep_action["reason"] == "exact_match_in_source"

        # confidence 1.0
        assert result["__validation__"]["confidence"]["비용상세.총액"] == 1.0


class TestCorrectAction:
    """교정 액션 테스트"""

    def test_correct_with_nearest_keyword(self):
        """근접도 기반 교정"""
        json_data = {
            "비용상세": {"총액": 1_000_000}  # 잘못된 값
        }
        source_text = "합계: 1,230,000원"  # 실제 값

        result = validate_numeric_fields(json_data, source_text)

        actions = result["__validation__"]["actions"]
        correct_action = next((a for a in actions if a["action"] == "correct"), None)
        assert correct_action is not None
        assert correct_action["field"] == "비용상세.총액"
        assert correct_action["from"] == 1_000_000
        assert correct_action["to"] == 1_230_000
        assert correct_action["reason"] == "nearest_total_keyword"

        # 실제 값이 교정되었는지 확인
        assert result["비용상세"]["총액"] == 1_230_000

        # confidence 존재 확인 (0 < confidence <= 1)
        confidence = result["__validation__"]["confidence"]["비용상세.총액"]
        assert 0 < confidence <= 1.0


class TestRemoveAction:
    """삭제 액션 테스트"""

    def test_remove_not_found(self):
        """원문에 없는 금액 제거"""
        json_data = {
            "details": {"금액": 500_000}  # 원문에 명확히 없음
        }
        source_text = "가격 정보 없음"  # 금액 키워드도 없음

        result = validate_numeric_fields(json_data, source_text)

        actions = result["__validation__"]["actions"]
        remove_action = next((a for a in actions if a["action"] == "remove"), None)
        assert remove_action is not None
        assert remove_action["field"] == "details.금액"
        assert remove_action["from"] == 500_000
        assert remove_action["reason"] == "not_found_in_source"

        # 실제 값이 제거되었는지 확인
        assert result["details"]["금액"] == "정보 없음"

        # confidence 0.0
        assert result["__validation__"]["confidence"]["details.금액"] == 0.0


class TestConfidenceScores:
    """신뢰도 점수 테스트"""

    def test_confidence_exact_match(self):
        """정확 일치 → 1.0"""
        json_data = {
            "비용상세": {"총액": 1_000_000}
        }
        source_text = "총액: 1,000,000원"

        result = validate_numeric_fields(json_data, source_text)

        assert result["__validation__"]["confidence"]["비용상세.총액"] == 1.0

    def test_confidence_corrected(self):
        """교정 → 0 < conf < 1"""
        json_data = {
            "비용상세": {"총액": 999}
        }
        source_text = "총액: 1,000,000원"

        result = validate_numeric_fields(json_data, source_text)

        confidence = result["__validation__"]["confidence"]["비용상세.총액"]
        assert 0 < confidence < 1.0

    def test_confidence_removed(self):
        """제거 → 0.0"""
        json_data = {
            "details": {"금액": 123_456}
        }
        source_text = "다른 내용"

        result = validate_numeric_fields(json_data, source_text)

        # 제거 액션이 있으면 confidence 0.0
        remove_action = next(
            (a for a in result["__validation__"]["actions"] if a["action"] == "remove"),
            None
        )
        if remove_action:
            field = remove_action["field"]
            assert result["__validation__"]["confidence"][field] == 0.0


class TestMultipleFields:
    """복수 필드 동시 검증"""

    def test_multiple_fields_validation(self):
        """여러 필드 동시 검증"""
        json_data = {
            "비용상세": {
                "총액": 1_000_000,
                "단가": 500_000,
            }
        }
        source_text = """
        단가: 500,000원
        수량: 2
        합계: 1,000,000원
        """

        result = validate_numeric_fields(json_data, source_text)

        # 두 필드 모두 액션 존재
        actions = result["__validation__"]["actions"]
        assert len(actions) >= 2

        # 두 필드 모두 confidence 존재
        assert "비용상세.총액" in result["__validation__"]["confidence"]
        assert "비용상세.단가" in result["__validation__"]["confidence"]


class TestEdgeCases:
    """엣지 케이스"""

    def test_no_amounts_in_source(self):
        """원문에 금액 없음"""
        json_data = {
            "details": {"금액": 1_000_000}
        }
        source_text = "금액 정보가 없습니다"

        result = validate_numeric_fields(json_data, source_text)

        # source_amounts 빈 리스트
        assert result["__validation__"]["source_amounts"] == []

        # 제거 액션
        remove_action = next(
            (a for a in result["__validation__"]["actions"] if a["action"] == "remove"),
            None
        )
        assert remove_action is not None

    def test_no_numeric_fields_in_json(self):
        """JSON에 수치 필드 없음"""
        json_data = {
            "제목": "테스트 문서"
        }
        source_text = "총액: 1,000,000원"

        result = validate_numeric_fields(json_data, source_text)

        # __validation__ 존재하지만 actions 비어있음
        assert "__validation__" in result
        assert result["__validation__"]["actions"] == []

    def test_invalid_format_field(self):
        """잘못된 포맷 필드 (파싱 불가)"""
        json_data = {
            "details": {"금액": "잘못된 값"}
        }
        source_text = "금액: 1,000,000원"

        result = validate_numeric_fields(json_data, source_text)

        # 파싱 실패 → 액션 없음 (예외 무시)
        # 또는 빈 액션
        assert "__validation__" in result


class TestComplexScenario:
    """복잡한 시나리오"""

    def test_mixed_keep_correct_remove(self):
        """유지/교정/삭제 혼합"""
        json_data = {
            "details": {"금액": 500_000},  # 정확 일치 → keep
            "비용상세": {
                "총액": 1_000_000,  # 교정 가능 → correct
                "단가": 999_999,    # 교정 불가 → remove or keep (ambiguous)
            }
        }
        source_text = """
        금액: 500,000원
        합계: 1,200,000원
        """

        result = validate_numeric_fields(json_data, source_text)

        actions = result["__validation__"]["actions"]

        # keep 액션 (details.금액)
        keep_actions = [a for a in actions if a["action"] == "keep"]
        assert any(a["field"] == "details.금액" for a in keep_actions)

        # correct 액션 (비용상세.총액)
        correct_actions = [a for a in actions if a["action"] == "correct"]
        assert any(a["field"] == "비용상세.총액" for a in correct_actions)

        # confidence 다양성 확인
        confidences = result["__validation__"]["confidence"]
        assert confidences["details.금액"] == 1.0  # 정확 일치
        assert 0 < confidences["비용상세.총액"] < 1.0  # 교정
