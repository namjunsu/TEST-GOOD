"""
JSON 유틸리티 테스트 (Phase 1 개선사항)
"""
import pytest
from app.rag.utils.json_utils import (
    _extract_balanced_json_blocks,
    extract_last_json_block,
    parse_summary_json_robust,
    ensure_citations,
    _mask_sensitive_data,
)


class TestStringAwareParsing:
    """문자열 내부 중괄호 안전 처리 테스트"""

    def test_string_with_curly_braces(self):
        """문자열 내부에 중괄호가 있는 경우"""
        text = '{"name": "test { not json } inside", "value": 123}'
        blocks = _extract_balanced_json_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == text

    def test_multiple_json_objects(self):
        """여러 JSON 객체가 있는 경우"""
        text = '{"a": 1} some text {"b": 2}'
        blocks = _extract_balanced_json_blocks(text)
        assert len(blocks) == 2
        assert blocks[0] == '{"a": 1}'
        assert blocks[1] == '{"b": 2}'

    def test_nested_objects(self):
        """중첩된 객체"""
        text = '{"outer": {"inner": {"deep": "value"}}}'
        blocks = _extract_balanced_json_blocks(text)
        assert len(blocks) == 1
        result = extract_last_json_block(text)
        assert result["outer"]["inner"]["deep"] == "value"

    def test_escaped_quotes(self):
        """이스케이프된 따옴표"""
        text = r'{"message": "He said \"hello\" to me"}'
        blocks = _extract_balanced_json_blocks(text)
        assert len(blocks) == 1
        result = extract_last_json_block(text)
        assert 'He said "hello" to me' in result["message"]


class TestCodeBlockVariants:
    """코드블록 변형 대응 테스트"""

    def test_json_code_block(self):
        """기본 json 코드블록"""
        text = """
        ```json
        {"title": "테스트"}
        ```
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["title"] == "테스트"

    def test_jsonc_code_block(self):
        """jsonc 코드블록"""
        text = """
        ```jsonc
        {"title": "테스트"}
        ```
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["title"] == "테스트"

    def test_uppercase_code_block(self):
        """대문자 코드블록"""
        text = """
        ```JSONC
        {"title": "테스트"}
        ```
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["title"] == "테스트"

    def test_mixed_case_code_block(self):
        """혼합 케이스 코드블록"""
        text = """
        ```Jsonc
        {"title": "테스트"}
        ```
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["title"] == "테스트"

    def test_no_code_block(self):
        """코드블록 없이 평문 JSON"""
        text = '{"title": "테스트"}'
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["title"] == "테스트"


class TestTrailingCommaFix:
    """끝 콤마 제거 테스트"""

    def test_trailing_comma_object(self):
        """객체 끝 콤마"""
        text = '{"a": 1, "b": 2,}'
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["a"] == 1
        assert result["b"] == 2

    def test_trailing_comma_array(self):
        """배열 끝 콤마"""
        text = '{"items": [1, 2, 3,]}'
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["items"] == [1, 2, 3]


class TestRawDecodeBackup:
    """raw_decode 백업 경로 테스트"""

    def test_streaming_leftover(self):
        """스트리밍 잔재 처리"""
        text = 'Some prefix text {"valid": "json"} some suffix'
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["valid"] == "json"

    def test_multiple_objects_first_valid(self):
        """여러 객체 중 첫 번째 유효한 것 선택"""
        text = '{"first": 1} invalid json {"second": 2}'
        result = parse_summary_json_robust(text)
        assert result is not None
        # 첫 번째 균형 블록이 선택되어야 함
        assert "first" in result


class TestEnsureCitations:
    """citations 필드 보강 테스트"""

    def test_empty_citations(self):
        """빈 citations 리스트"""
        data = {"title": "테스트"}
        result = ensure_citations(data, "test_doc.pdf")
        assert "citations" in result
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source"] == "test_doc.pdf"

    def test_duplicate_prevention(self):
        """중복 방지"""
        data = {
            "title": "테스트",
            "citations": [
                {"source": "test_doc.pdf", "pages": "1-5"}
            ]
        }
        result = ensure_citations(data, "test_doc.pdf")
        # 중복 추가되지 않아야 함
        assert len(result["citations"]) == 1

    def test_non_list_citations(self):
        """citations가 리스트가 아닌 경우"""
        data = {"title": "테스트", "citations": "invalid"}
        result = ensure_citations(data, "test_doc.pdf")
        # 리스트로 초기화되어야 함
        assert isinstance(result["citations"], list)
        assert len(result["citations"]) == 1

    def test_no_doc_ref(self):
        """doc_ref가 없는 경우"""
        data = {"title": "테스트"}
        result = ensure_citations(data, None)
        assert "citations" in result
        # doc_ref가 없으면 빈 리스트
        assert result["citations"] == []


class TestSensitiveDataMasking:
    """민감정보 마스킹 테스트"""

    def test_amount_masking(self):
        """금액 필드 마스킹"""
        data = {"title": "테스트", "금액": 1000000, "총액": 2000000}
        masked = _mask_sensitive_data(data, max_length=500)
        assert "***" in masked
        assert "1000000" not in masked

    def test_max_length_limit(self):
        """최대 길이 제한"""
        data = {"a" * 100: "b" * 100}
        masked = _mask_sensitive_data(data, max_length=50)
        assert len(masked) <= 53  # 50 + "..."

    def test_nested_structure(self):
        """중첩 구조 마스킹"""
        data = {"금액": 1000000, "상세": {"단가": 50000}}
        masked = _mask_sensitive_data(data, max_length=500)
        assert "***" in masked
        assert "<dict>" in masked


class TestComplexScenarios:
    """복잡한 시나리오 테스트"""

    def test_llm_response_with_explanation(self):
        """설명이 포함된 LLM 응답"""
        text = """
        여기 JSON 결과입니다:

        ```json
        {
            "제목": "DVR 교체",
            "금액": 1000000,
            "상세": {
                "단가": 500000,
                "수량": 2
            }
        }
        ```

        이상입니다.
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        assert result["제목"] == "DVR 교체"
        assert result["금액"] == 1000000

    def test_multiple_json_blocks_select_first(self):
        """여러 JSON 블록 중 첫 번째 선택"""
        text = """
        ```json
        {"valid": true, "data": "first"}
        ```

        ```json
        {"valid": true, "data": "second"}
        ```
        """
        result = parse_summary_json_robust(text)
        assert result is not None
        # 첫 번째 블록이 선택되어야 함
        assert result["data"] == "first"
