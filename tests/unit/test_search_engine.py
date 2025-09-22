"""
Unit tests for Search Engine
"""

import pytest
from unittest.mock import Mock, patch
from concurrent.futures import Future
from rag_modules.search.engine import SearchEngine
from rag_modules.core.config import ParallelConfig

class TestSearchEngine:
    """SearchEngine 단위 테스트"""

    @pytest.fixture
    def search_engine(self):
        """검색 엔진 fixture"""
        config = ParallelConfig(max_workers=2, timeout=5)
        return SearchEngine(config)

    def test_search_empty_documents(self, search_engine):
        """빈 문서 리스트 검색 테스트"""
        results = search_engine.search("test query", [])
        assert results == []

    def test_calculate_relevance(self, search_engine):
        """관련성 점수 계산 테스트"""
        # Given
        document = {'content': 'This is a test document with test content'}

        # When
        score = search_engine._calculate_relevance('test', document)

        # Then
        assert score > 0
        assert score == 4.0  # 'test' appears twice, each worth 2 points

    def test_search_with_results(self, search_engine):
        """검색 결과 테스트"""
        # Given
        documents = [
            {'content': 'Document about Python programming'},
            {'content': 'Document about Java programming'},
            {'content': 'Python is great for data science'}
        ]

        # When
        results = search_engine.search('Python', documents)

        # Then
        assert len(results) == 2
        assert results[0]['score'] > results[1]['score'] if len(results) > 1 else True

    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_parallel_search(self, mock_executor, search_engine):
        """병렬 검색 테스트"""
        # Given
        documents = [{'content': 'test'}]
        mock_future = Mock(spec=Future)
        mock_future.result.return_value = {'document': documents[0], 'score': 2.0}
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

        # When
        results = search_engine._parallel_search('test', documents)

        # Then
        assert len(results) > 0
