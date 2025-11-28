"""RAG Pipeline 테스트

pipeline.py의 핵심 기능 테스트:
- query() 메서드
- answer() 메서드
- 모드 결정 로직
- 캐싱 로직
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from app.rag.contracts import RAGResponse


class TestRAGPipelineInit:
    """RAGPipeline 초기화 테스트"""

    def test_init_with_defaults(self):
        """기본 컴포넌트로 초기화"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            assert pipeline.retriever is not None
            assert pipeline.compressor is not None
            assert pipeline.generator is not None
            assert pipeline.query_router is not None

    def test_init_with_custom_retriever(self):
        """커스텀 retriever로 초기화"""
        mock_retriever = Mock()

        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline(retriever=mock_retriever)

            assert pipeline.retriever == mock_retriever


class TestValidateQueryInput:
    """쿼리 입력 검증 테스트"""

    @pytest.fixture
    def pipeline(self):
        """테스트용 파이프라인 인스턴스"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            return RAGPipeline()

    def test_empty_query(self, pipeline):
        """빈 쿼리 검증"""
        result = pipeline._validate_query_input("")
        assert result is not None
        assert result.success is False
        assert result.error == "빈 질문입니다"

    def test_whitespace_query(self, pipeline):
        """공백만 있는 쿼리 검증"""
        result = pipeline._validate_query_input("   ")
        assert result is not None
        assert result.success is False

    def test_valid_query(self, pipeline):
        """유효한 쿼리 검증"""
        result = pipeline._validate_query_input("테스트 질문")
        assert result is None  # 유효하면 None 반환


class TestQueryMethod:
    """query() 메서드 테스트"""

    def test_query_empty_input(self):
        """빈 입력에 대한 query()"""
        with patch("app.rag.pipeline.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            response = pipeline.query("")
            assert response.success is False
            assert response.error == "빈 질문입니다"

    def test_query_no_results(self):
        """검색 결과 없음"""
        with patch("app.rag.pipeline.RAGPipelineFactory") as mock_factory:
            mock_retriever = Mock()
            mock_retriever.search.return_value = []

            mock_factory.create_retriever.return_value = mock_retriever
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            response = pipeline.query("존재하지 않는 문서")
            assert response.success is True
            assert "검색되지 않았다" in response.answer

    def test_query_with_results(self):
        """검색 결과 있음"""
        with patch("app.rag.pipeline.RAGPipelineFactory") as mock_factory:
            mock_retriever = Mock()
            mock_compressor = Mock()
            mock_generator = Mock()

            # 검색 결과 모킹
            mock_results = [
                {"doc_id": "doc1", "score": 0.9, "snippet": "테스트 문서 내용"},
                {"doc_id": "doc2", "score": 0.8, "snippet": "다른 문서 내용"},
            ]
            mock_retriever.search.return_value = mock_results
            mock_compressor.compress.return_value = mock_results
            mock_generator.generate.return_value = "생성된 답변입니다."

            mock_factory.create_retriever.return_value = mock_retriever
            mock_factory.create_compressor.return_value = mock_compressor
            mock_factory.create_generator.return_value = mock_generator
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            response = pipeline.query("테스트 질문", top_k=5)

            assert response.success is True
            assert response.answer == "생성된 답변입니다."
            assert len(response.raw_results) == 2
            mock_retriever.search.assert_called_once()


class TestDetermineRagMode:
    """모드 결정 로직 테스트"""

    @pytest.fixture
    def pipeline(self):
        """테스트용 파이프라인"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            return RAGPipeline()

    def test_force_chat_mode_smalltalk(self, pipeline):
        """스몰토크는 CHAT 모드"""
        with patch("app.rag.pipeline.settings") as mock_settings:
            mock_settings.MODE = "AUTO"

            with patch("app.rag.pipeline.force_chat_mode") as mock_force:
                mock_force.return_value = (True, "smalltalk")

                metrics = {}
                results = [{"score": 0.9}]
                mode = pipeline._determine_rag_mode("안녕하세요", results, metrics)

                assert mode == "chat"
                assert metrics["mode"] == "chat"
                assert metrics["force_chat_reason"] == "smalltalk"

    def test_chat_mode_env(self, pipeline):
        """CHAT 환경 설정"""
        with patch("app.rag.pipeline.settings") as mock_settings:
            mock_settings.MODE = "CHAT"

            metrics = {}
            results = [{"score": 0.9}]
            mode = pipeline._determine_rag_mode("테스트", results, metrics)

            assert mode == "chat"
            assert metrics["top_score"] == 0.0

    def test_rag_mode_env(self, pipeline):
        """RAG 환경 설정"""
        with patch("app.rag.pipeline.settings") as mock_settings:
            mock_settings.MODE = "RAG"

            metrics = {}
            results = [{"score": 0.85}]
            mode = pipeline._determine_rag_mode("문서 검색", results, metrics)

            assert mode == "rag"
            assert metrics["top_score"] == 0.85


class TestAnswerMethod:
    """answer() 메서드 테스트"""

    @pytest.fixture
    def mock_pipeline(self):
        """모킹된 파이프라인"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_retriever = Mock()
            mock_compressor = Mock()
            mock_generator = Mock()

            mock_factory.create_retriever.return_value = mock_retriever
            mock_factory.create_compressor.return_value = mock_compressor
            mock_factory.create_generator.return_value = mock_generator
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            return pipeline, mock_retriever, mock_compressor, mock_generator

    def test_answer_cache_hit_memory(self, mock_pipeline):
        """메모리 캐시 히트"""
        pipeline, _, _, _ = mock_pipeline

        cached_result = {
            "text": "캐시된 답변",
            "citations": [],
            "evidence": [],
            "status": {"retrieved_count": 1, "selected_count": 1, "found": True},
        }

        with patch("app.rag.pipeline.get_cached_result") as mock_cache:
            mock_cache.return_value = cached_result

            result = pipeline.answer("테스트 질문")

            assert result["text"] == "캐시된 답변"
            assert result["status"]["from_cache"] == "memory"

    def test_answer_cache_hit_persistent(self, mock_pipeline):
        """영구 캐시 히트"""
        pipeline, _, _, _ = mock_pipeline

        cached_result = {
            "text": "영구 캐시 답변",
            "citations": [],
            "evidence": [],
            "status": {"retrieved_count": 1, "selected_count": 1, "found": True},
        }

        with patch("app.rag.pipeline.get_cached_result") as mock_mem_cache:
            mock_mem_cache.return_value = None

            with patch("app.rag.pipeline.get_cached_result_persistent") as mock_persist:
                mock_persist.return_value = cached_result

                with patch("app.rag.pipeline.cache_query_result"):
                    result = pipeline.answer("테스트 질문")

                    assert result["text"] == "영구 캐시 답변"
                    assert result["status"]["from_cache"] == "persistent"

    def test_answer_returns_citations(self, mock_pipeline):
        """citations 포맷 확인"""
        pipeline, mock_retriever, mock_compressor, mock_generator = mock_pipeline

        mock_results = [
            {"doc_id": "doc1", "score": 0.9, "snippet": "내용1", "page": 1},
        ]
        mock_retriever.search.return_value = mock_results
        mock_compressor.compress.return_value = mock_results
        mock_generator.generate.return_value = "답변"

        with patch("app.rag.pipeline.get_cached_result", return_value=None):
            with patch("app.rag.pipeline.get_cached_result_persistent", return_value=None):
                with patch("app.rag.pipeline.cache_query_result"):
                    with patch("app.rag.pipeline.cache_query_result_persistent"):
                        result = pipeline.answer("테스트")

                        assert "text" in result
                        assert "citations" in result
                        assert "evidence" in result
                        assert "status" in result


class TestAnswerText:
    """answer_text() 메서드 테스트"""

    def test_answer_text_returns_string(self):
        """answer_text는 문자열만 반환"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()

            with patch.object(pipeline, "answer") as mock_answer:
                mock_answer.return_value = {"text": "테스트 답변", "citations": []}

                result = pipeline.answer_text("질문")

                assert isinstance(result, str)
                assert result == "테스트 답변"


class TestBuildRagResponse:
    """_build_rag_response() 테스트"""

    @pytest.fixture
    def pipeline(self):
        """테스트용 파이프라인"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            return RAGPipeline()

    def test_chat_mode_no_sources(self, pipeline):
        """CHAT 모드에서는 출처 제거"""
        import time

        results = [{"doc_id": "doc1", "score": 0.9}]
        compressed = [{"doc_id": "doc1", "snippet": "내용"}]
        metrics = {"search_time": 0.1, "compress_time": 0.1, "generate_time": 0.1}

        response = pipeline._build_rag_response(
            query="테스트",
            answer="답변",
            results=results,
            compressed=compressed,
            determined_mode="chat",
            start_time=time.perf_counter() - 0.5,
            metrics=metrics,
            diagnostics={},
        )

        assert response.source_docs == []
        assert response.evidence_chunks == []

    def test_rag_mode_has_sources(self, pipeline):
        """RAG 모드에서는 출처 포함"""
        import time

        results = [{"doc_id": "doc1", "score": 0.9}]
        compressed = [{"doc_id": "doc1", "snippet": "내용"}]
        metrics = {"search_time": 0.1, "compress_time": 0.1, "generate_time": 0.1}

        response = pipeline._build_rag_response(
            query="테스트",
            answer="답변",
            results=results,
            compressed=compressed,
            determined_mode="rag",
            start_time=time.perf_counter() - 0.5,
            metrics=metrics,
            diagnostics={},
        )

        assert len(response.source_docs) > 0
        assert len(response.evidence_chunks) > 0


class TestMakeResponse:
    """_make_response() 테스트"""

    @pytest.fixture
    def pipeline(self):
        """테스트용 파이프라인"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            return RAGPipeline()

    def test_response_format(self, pipeline):
        """응답 포맷 검증"""
        selected = [
            {"doc_id": "doc1", "filename": "test.pdf", "page": 1, "snippet": "내용"},
        ]
        retrieved = [{"doc_id": "doc1"}]

        response = pipeline._make_response("답변 텍스트", selected, retrieved)

        assert "text" in response
        assert "citations" in response
        assert "evidence" in response
        assert "status" in response
        assert response["text"] == "답변 텍스트"
        assert len(response["citations"]) == 1
        assert response["status"]["found"] is True

    def test_empty_selected(self, pipeline):
        """선택된 문서 없음"""
        response = pipeline._make_response("답변", [], [])

        assert response["status"]["found"] is False
        assert response["status"]["selected_count"] == 0


class TestHandlerDelegation:
    """핸들러 위임 테스트"""

    @pytest.fixture
    def pipeline(self):
        """테스트용 파이프라인"""
        with patch("app.rag.factory.RAGPipelineFactory") as mock_factory:
            mock_factory.create_retriever.return_value = Mock()
            mock_factory.create_compressor.return_value = Mock()
            mock_factory.create_generator.return_value = Mock()
            mock_factory.load_known_drafters.return_value = set()

            from app.rag.pipeline import RAGPipeline
            return RAGPipeline()

    def test_answer_search_delegates(self, pipeline):
        """_answer_search가 SearchHandler에 위임"""
        mock_result = {"text": "검색 결과"}
        pipeline._search_handler = Mock()
        pipeline._search_handler.handle.return_value = mock_result

        result = pipeline._answer_search("검색 질문")

        pipeline._search_handler.handle.assert_called_once_with("검색 질문")
        assert result == mock_result

    def test_answer_document_delegates(self, pipeline):
        """_answer_document가 DocumentHandler에 위임"""
        mock_result = {"text": "문서 내용"}
        pipeline._document_handler = Mock()
        pipeline._document_handler.handle.return_value = mock_result

        result = pipeline._answer_document("문서 질문", selected_filename="test.pdf")

        pipeline._document_handler.handle.assert_called_once_with(
            "문서 질문", selected_filename="test.pdf",
        )
        assert result == mock_result

    def test_answer_cost_sum_delegates(self, pipeline):
        """_answer_cost_sum이 CostSumHandler에 위임"""
        mock_result = {"text": "비용 합계"}
        pipeline._cost_sum_handler = Mock()
        pipeline._cost_sum_handler.handle.return_value = mock_result

        result = pipeline._answer_cost_sum("비용 질문")

        pipeline._cost_sum_handler.handle.assert_called_once_with("비용 질문")
        assert result == mock_result
