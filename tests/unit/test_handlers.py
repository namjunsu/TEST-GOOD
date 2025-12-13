"""핸들러 모듈 테스트

app/rag/handlers/ 모듈의 단위 테스트.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestResponseBuilderFunctions:
    """response.py 함수 테스트"""

    def test_is_smalltalk_patterns(self):
        """스몰토크 패턴 감지 테스트"""
        from app.rag.handlers import is_smalltalk

        # 스몰토크로 감지되어야 함
        assert is_smalltalk("안녕") is True
        assert is_smalltalk("안녕하세요") is True
        assert is_smalltalk("hi") is True
        assert is_smalltalk("hello") is True
        assert is_smalltalk("감사합니다") is True

        # 스몰토크가 아님
        assert is_smalltalk("중계차 문서") is False
        assert is_smalltalk("카메라 렌즈 오버홀") is False
        assert is_smalltalk("2025년 문서 찾아줘") is False

    def test_force_chat_mode(self):
        """강제 CHAT 모드 판단 테스트"""
        from app.rag.handlers import force_chat_mode

        # 스몰토크 → CHAT 모드
        should_force, reason = force_chat_mode("안녕")
        assert should_force is True
        assert reason == "smalltalk"

        # 단순 산술 → CHAT 모드
        should_force, reason = force_chat_mode("1+1")
        assert should_force is True
        assert reason == "simple_math"

        # 도메인 쿼리 → RAG 모드
        should_force, reason = force_chat_mode("중계차 카메라 문서")
        assert should_force is False
        assert reason == ""

    def test_format_title_from_filename(self):
        """파일명에서 제목 추출 테스트"""
        from app.rag.handlers import format_title_from_filename

        # 날짜 접두어 제거
        assert format_title_from_filename("2025-01-01_테스트_문서.pdf") == "테스트 문서"

        # 언더스코어 → 공백
        assert format_title_from_filename("중계차_카메라_렌즈_오버홀.pdf") == "중계차 카메라 렌즈 오버홀"

        # 대소문자 확장자
        assert format_title_from_filename("test.PDF") == "test"

    def test_build_file_path(self):
        """파일 경로 생성 테스트"""
        from app.rag.handlers import build_file_path

        # 연도가 있는 파일
        assert build_file_path("2025-01-01_test.pdf") == "docs/year_2025/2025-01-01_test.pdf"

        # 연도가 없는 파일
        assert build_file_path("test.pdf") == "docs/test.pdf"

    def test_build_standard_response(self):
        """표준 응답 생성 테스트"""
        from app.rag.handlers import build_standard_response

        response = build_standard_response(
            mode="SEARCH",
            text="테스트 결과",
            files=["test.pdf"],
            count=1,
            found=True
        )

        assert response["mode"] == "SEARCH"
        assert response["text"] == "테스트 결과"
        assert response["files"] == ["test.pdf"]
        assert response["count"] == 1
        assert response["status"]["found"] is True
        assert "citations" in response
        assert "evidence" in response

    def test_build_error_response(self):
        """에러 응답 생성 테스트"""
        from app.rag.handlers import build_error_response

        response = build_error_response(
            mode="SEARCH",
            error="테스트 에러"
        )

        assert response["mode"] == "SEARCH"
        assert "오류:" in response["text"]
        assert response["count"] == 0
        assert response["status"]["found"] is False

    def test_clean_ui_metadata(self):
        """UI 메타데이터 제거 테스트"""
        from app.rag.handlers import clean_ui_metadata

        # 메타데이터 태그가 있는 쿼리
        query = "중계차 🏷 pdf · 📅 2024-10-24 · ✍ 최새름 문서 요약해줘"
        cleaned = clean_ui_metadata(query)

        assert "🏷" not in cleaned
        assert "📅" not in cleaned
        assert "✍" not in cleaned
        assert "중계차" in cleaned
        # Note: clean_ui_metadata 함수는 ✍ 뒤의 모든 텍스트를 제거함
        # 이는 UI 복사 시 메타데이터가 맨 뒤에 붙는 패턴에 맞춤

        # 메타데이터가 없는 경우 그대로 유지
        plain_query = "중계차 카메라 문서 요약해줘"
        assert clean_ui_metadata(plain_query) == plain_query

    def test_normalize_chunk_text(self):
        """청크 텍스트 정규화 테스트"""
        from app.rag.handlers import normalize_chunk_text

        # snippet 우선
        result = {"snippet": "SNIPPET", "content": "CONTENT", "text": "TEXT"}
        assert normalize_chunk_text(result) == "snippet"

        # content 폴백
        result = {"content": "CONTENT", "text": "TEXT"}
        assert normalize_chunk_text(result) == "content"

        # text 폴백
        result = {"text": "TEXT"}
        assert normalize_chunk_text(result) == "text"

        # 빈 결과
        result = {}
        assert normalize_chunk_text(result) == ""


class TestBaseHandler:
    """BaseHandler 테스트"""

    def test_handler_response_to_dict(self):
        """HandlerResponse.to_dict() 테스트"""
        from app.rag.handlers import HandlerResponse

        response = HandlerResponse(
            mode="TEST",
            text="테스트 응답",
            files=["test.pdf"],
            count=1
        )

        d = response.to_dict()

        assert d["mode"] == "TEST"
        assert d["text"] == "테스트 응답"
        assert d["files"] == ["test.pdf"]
        assert d["count"] == 1
        assert "citations" in d
        assert "evidence" in d
        assert "status" in d

    def test_handler_response_defaults(self):
        """HandlerResponse 기본값 테스트"""
        from app.rag.handlers import HandlerResponse

        response = HandlerResponse(
            mode="TEST",
            text="테스트",
            files=[],
            count=0
        )

        assert response.citations == []
        assert response.evidence == []
        assert response.status["found"] is False
        assert response.latency_ms == 0.0


class TestSearchHandler:
    """SearchHandler 테스트 (모킹)"""

    def test_search_handler_mode(self):
        """SearchHandler 모드 확인"""
        from app.rag.handlers import SearchHandler

        assert SearchHandler.mode == "SEARCH"

    def test_search_handler_init(self):
        """SearchHandler 초기화 테스트"""
        from app.rag.handlers import SearchHandler

        # Mock pipeline
        mock_pipeline = Mock()
        mock_pipeline.retriever = Mock()
        mock_pipeline.generator = Mock()

        handler = SearchHandler(mock_pipeline)

        assert handler.pipeline == mock_pipeline
        assert handler.retriever == mock_pipeline.retriever


class TestDocumentHandler:
    """DocumentHandler 테스트 (모킹)"""

    def test_document_handler_mode(self):
        """DocumentHandler 모드 확인"""
        from app.rag.handlers import DocumentHandler

        assert DocumentHandler.mode == "DOCUMENT"

    def test_document_handler_init(self):
        """DocumentHandler 초기화 테스트"""
        from app.rag.handlers import DocumentHandler

        # Mock pipeline
        mock_pipeline = Mock()
        mock_pipeline.retriever = Mock()
        mock_pipeline.generator = Mock()

        handler = DocumentHandler(mock_pipeline)

        assert handler.pipeline == mock_pipeline


class TestCostSumHandler:
    """CostSumHandler 테스트 (모킹)"""

    def test_cost_sum_handler_mode(self):
        """CostSumHandler 모드 확인"""
        from app.rag.handlers import CostSumHandler

        assert CostSumHandler.mode == "COST_SUM"


class TestHandlerModuleExports:
    """handlers 모듈 export 테스트"""

    def test_all_handlers_exported(self):
        """모든 핸들러 클래스가 export되는지 확인"""
        from app.rag import handlers

        assert hasattr(handlers, "BaseHandler")
        assert hasattr(handlers, "HandlerResponse")
        assert hasattr(handlers, "SearchHandler")
        assert hasattr(handlers, "CostSumHandler")
        assert hasattr(handlers, "DocumentHandler")

    def test_all_functions_exported(self):
        """모든 유틸리티 함수가 export되는지 확인"""
        from app.rag import handlers

        # 쿼리 분류 함수
        assert hasattr(handlers, "is_smalltalk")
        assert hasattr(handlers, "is_simple_math")
        assert hasattr(handlers, "force_chat_mode")

        # 파일/경로 함수
        assert hasattr(handlers, "format_title_from_filename")
        assert hasattr(handlers, "build_file_path")

        # 응답 빌더 함수
        assert hasattr(handlers, "build_standard_response")
        assert hasattr(handlers, "build_error_response")
        assert hasattr(handlers, "build_empty_response")
