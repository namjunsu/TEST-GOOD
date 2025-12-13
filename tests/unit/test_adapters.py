"""RAG 어댑터 테스트

adapters.py의 폴백 및 어댑터 클래스 테스트:
- _DummyRetriever: 더미 검색기
- _NoOpCompressor: No-op 압축기
- _DummyGenerator: 더미 생성기
- _LLMAdapter: QwenLLM 래퍼
- _QuickFixGenerator: QuickFixRAG 래퍼
- _V2RetrieverAdapter: V2 검색기 어댑터
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.rag.adapters import (
    _DummyGenerator,
    _DummyRetriever,
    _LLMAdapter,
    _NoOpCompressor,
    _QuickFixGenerator,
    _V2RetrieverAdapter,
)


class TestDummyRetriever:
    """더미 검색기 테스트"""

    def test_search_returns_empty_list(self):
        """search()는 항상 빈 리스트 반환"""
        retriever = _DummyRetriever()
        result = retriever.search("테스트 쿼리", top_k=5)
        assert result == []

    def test_search_with_all_params(self):
        """모든 파라미터를 전달해도 빈 리스트 반환"""
        retriever = _DummyRetriever()
        result = retriever.search(
            "테스트",
            top_k=10,
            mode="rag",
            selected_filename="test.pdf",
            strict_content=True,
        )
        assert result == []


class TestNoOpCompressor:
    """No-op 압축기 테스트"""

    def test_compress_returns_input(self):
        """compress()는 입력을 그대로 반환"""
        compressor = _NoOpCompressor()
        chunks = [
            {"doc_id": "doc1", "snippet": "내용1"},
            {"doc_id": "doc2", "snippet": "내용2"},
        ]
        result = compressor.compress(chunks, ratio=0.5)
        assert result == chunks

    def test_compress_empty_list(self):
        """빈 리스트도 그대로 반환"""
        compressor = _NoOpCompressor()
        result = compressor.compress([], ratio=0.5)
        assert result == []


class TestDummyGenerator:
    """더미 생성기 테스트"""

    def test_generate_returns_error_message(self):
        """generate()는 에러 메시지 반환"""
        generator = _DummyGenerator()
        result = generator.generate("질문", "컨텍스트", temperature=0.7)
        assert "[E_GENERATE]" in result
        assert "비활성" in result

    def test_generate_with_mode(self):
        """모드 파라미터를 전달해도 동일하게 동작"""
        generator = _DummyGenerator()
        result = generator.generate("질문", "컨텍스트", temperature=0.7, mode="chat")
        assert "[E_GENERATE]" in result


class TestLLMAdapter:
    """LLM 어댑터 테스트"""

    def test_init_stores_llm(self):
        """초기화 시 llm 저장"""
        mock_llm = Mock()
        adapter = _LLMAdapter(mock_llm)
        assert adapter.llm == mock_llm

    def test_generate_from_context_success(self):
        """컨텍스트 기반 생성 성공"""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.answer = "생성된 답변입니다."
        mock_llm.generate_response.return_value = mock_response

        adapter = _LLMAdapter(mock_llm)
        result = adapter.generate_from_context(
            query="테스트 질문",
            context="테스트 컨텍스트",
            temperature=0.1,
            mode="rag",
        )

        assert result == "생성된 답변입니다."
        mock_llm.generate_response.assert_called_once()

    def test_generate_from_context_no_answer_attr(self):
        """응답에 answer 속성이 없으면 str 변환"""
        mock_llm = Mock()
        mock_llm.generate_response.return_value = "직접 문자열 응답"

        adapter = _LLMAdapter(mock_llm)
        result = adapter.generate_from_context("질문", "컨텍스트", 0.1)

        assert result == "직접 문자열 응답"

    def test_generate_from_context_exception(self):
        """생성 실패 시 에러 메시지 반환"""
        mock_llm = Mock()
        mock_llm.generate_response.side_effect = Exception("LLM 오류")

        adapter = _LLMAdapter(mock_llm)
        result = adapter.generate_from_context("질문", "컨텍스트", 0.1)

        assert "[E_GENERATE]" in result
        assert "LLM 오류" in result


class TestQuickFixGenerator:
    """QuickFix 생성기 테스트"""

    def test_init_stores_rag(self):
        """초기화 시 rag 저장"""
        mock_rag = Mock()
        generator = _QuickFixGenerator(mock_rag)
        assert generator.rag == mock_rag
        assert generator.compressed_chunks is None

    def test_generate_with_generate_from_context(self):
        """generate_from_context 메서드가 있으면 사용"""
        mock_rag = Mock()
        mock_rag.generate_from_context.return_value = "컨텍스트 기반 답변"

        generator = _QuickFixGenerator(mock_rag)
        result = generator.generate("질문", "컨텍스트", 0.7, mode="rag")

        assert result == "컨텍스트 기반 답변"
        mock_rag.generate_from_context.assert_called_once_with(
            "질문", "컨텍스트", temperature=0.7, mode="rag",
        )

    def test_generate_with_llm_and_compressed_chunks(self):
        """llm.generate_response 사용 + compressed_chunks"""
        mock_rag = Mock(spec=["_ensure_llm_loaded", "llm"])
        mock_rag.llm = Mock()
        mock_response = Mock()
        mock_response.answer = "LLM 답변"
        mock_rag.llm.generate_response.return_value = mock_response

        generator = _QuickFixGenerator(mock_rag)
        generator.compressed_chunks = [{"snippet": "청크1"}, {"snippet": "청크2"}]

        result = generator.generate("질문", "컨텍스트", 0.7, mode="rag")

        assert result == "LLM 답변"
        mock_rag._ensure_llm_loaded.assert_called_once()
        mock_rag.llm.generate_response.assert_called_once()

    def test_generate_with_llm_no_compressed_chunks(self):
        """llm.generate_response 사용, compressed_chunks 없음 (폴백)"""
        mock_rag = Mock(spec=["_ensure_llm_loaded", "llm"])
        mock_rag.llm = Mock()
        mock_response = Mock()
        mock_response.answer = "폴백 답변"
        mock_rag.llm.generate_response.return_value = mock_response

        generator = _QuickFixGenerator(mock_rag)
        # compressed_chunks = None (기본값)

        result = generator.generate("질문", "청크1\n\n청크2", 0.7, mode="rag")

        assert result == "폴백 답변"
        mock_rag.llm.generate_response.assert_called_once()

    def test_generate_with_answer_fallback(self):
        """최후 수단: rag.answer 사용"""
        mock_rag = Mock(spec=["answer"])
        mock_rag.answer.return_value = "answer 폴백"

        generator = _QuickFixGenerator(mock_rag)
        result = generator.generate("질문", "컨텍스트", 0.7)

        assert result == "answer 폴백"
        mock_rag.answer.assert_called_once_with("질문", use_llm_summary=True)

    def test_generate_rag_is_none(self):
        """rag가 None이면 에러 메시지"""
        generator = _QuickFixGenerator(None)
        result = generator.generate("질문", "컨텍스트", 0.7)

        # ERROR_RAG_UNAVAILABLE 메시지 확인
        assert "[E_GENERATE]" in result
        assert "사용할 수 없" in result

    def test_generate_exception(self):
        """생성 실패 시 에러 메시지"""
        mock_rag = Mock()
        mock_rag.generate_from_context.side_effect = Exception("생성 오류")

        generator = _QuickFixGenerator(mock_rag)
        result = generator.generate("질문", "컨텍스트", 0.7)

        assert "[E_GENERATE]" in result
        assert "생성 오류" in result


class TestV2RetrieverAdapter:
    """V2 검색기 어댑터 테스트"""

    def test_init_stores_v2_retriever(self):
        """초기화 시 v2_retriever 저장"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        adapter = _V2RetrieverAdapter(mock_v2)
        assert adapter.v2_retriever == mock_v2
        assert adapter.db == mock_v2.db

    def test_search_converts_v2_to_v1_format(self):
        """v2 결과를 v1 형식으로 변환"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.db.get_content.return_value = None

        # snippet이 50자 이상이어야 폴백하지 않음
        long_snippet = "테스트 내용입니다. 이것은 충분히 긴 스니펫입니다. " * 3

        mock_v2.search.return_value = {
            "fused_results": [
                {
                    "id": "doc_001",
                    "score": 0.95,
                    "filename": "test.pdf",
                    "title": "테스트 문서",
                    "date": "2024-01-01",
                    "snippet": long_snippet,
                },
            ],
        }

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert len(results) == 1
        assert results[0]["doc_id"] == "doc_001"
        assert results[0]["snippet"] == long_snippet
        assert results[0]["score"] == 0.95
        assert results[0]["page"] == 1
        assert results[0]["meta"]["filename"] == "test.pdf"

    def test_search_uses_content_as_snippet(self):
        """snippet이 없으면 content 사용"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.db.get_content.return_value = None

        mock_v2.search.return_value = {
            "fused_results": [
                {
                    "id": "doc_002",
                    "score": 0.8,
                    "content": "이것은 긴 콘텐츠입니다. " * 50,  # 500자 이상
                },
            ],
        }

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert len(results) == 1
        # content가 500자로 잘림
        assert len(results[0]["snippet"]) <= 500

    def test_search_fetches_content_from_db(self):
        """snippet이 짧으면 DB에서 content 조회"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.db.get_content.return_value = "DB에서 가져온 긴 콘텐츠입니다. " * 20

        mock_v2.search.return_value = {
            "fused_results": [
                {
                    "id": "doc_003",
                    "score": 0.7,
                    "snippet": "짧음",  # 50자 미만
                },
            ],
        }

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert len(results) == 1
        assert "DB에서 가져온" in results[0]["snippet"]
        mock_v2.db.get_content.assert_called_once_with("doc_003")

    def test_search_metadata_fallback(self):
        """snippet, content, DB 모두 없으면 메타데이터 폴백"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.db.get_content.return_value = None

        mock_v2.search.return_value = {
            "fused_results": [
                {
                    "id": "doc_004",
                    "score": 0.6,
                    "title": "테스트 제목",
                    "filename": "document.pdf",
                    "date": "2024-02-01",
                },
            ],
        }

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert len(results) == 1
        assert "테스트 제목" in results[0]["snippet"]
        assert "document.pdf" in results[0]["snippet"]

    def test_search_empty_results(self):
        """검색 결과 없음"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.search.return_value = {"fused_results": []}

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert results == []

    def test_search_exception(self):
        """검색 실패 시 빈 리스트 반환"""
        mock_v2 = Mock()
        mock_v2.db = Mock()
        mock_v2.search.side_effect = Exception("검색 오류")

        adapter = _V2RetrieverAdapter(mock_v2)
        results = adapter.search("테스트", top_k=5)

        assert results == []

    def test_warmup_is_noop(self):
        """warmup은 no-op"""
        mock_v2 = Mock()
        mock_v2.db = Mock()

        adapter = _V2RetrieverAdapter(mock_v2)
        adapter.warmup()  # 예외 없이 실행되어야 함
