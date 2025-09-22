"""
Integration tests for RAG System
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch

# Import after adding to path
import sys
sys.path.append('.')
from perfect_rag_modular import PerfectRAG
from rag_modules.core.config import RAGConfig

class TestRAGSystemIntegration:
    """RAG 시스템 통합 테스트"""

    @pytest.fixture
    def temp_docs_dir(self):
        """임시 문서 디렉토리"""
        temp_dir = tempfile.mkdtemp()
        docs_dir = Path(temp_dir) / 'docs'
        docs_dir.mkdir()

        # 테스트 문서 생성
        test_doc = docs_dir / 'test.txt'
        test_doc.write_text('2024년 장비 구매 기안서 내용')

        yield docs_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def rag_system(self, temp_docs_dir):
        """RAG 시스템 fixture"""
        config = RAGConfig(docs_dir=temp_docs_dir)
        return PerfectRAG(config)

    @pytest.mark.integration
    def test_end_to_end_search(self, rag_system):
        """종단 간 검색 테스트"""
        # When
        result = rag_system.search("장비 구매")

        # Then
        assert result is not None
        assert "검색 결과" in result or "test.txt" in result

    @pytest.mark.integration
    def test_cache_integration(self, rag_system):
        """캐시 통합 테스트"""
        # Given
        query = "테스트 쿼리"

        # When - 첫 번째 검색
        result1 = rag_system.search(query)

        # When - 두 번째 검색 (캐시 히트)
        result2 = rag_system.search(query)

        # Then
        assert result1 == result2

    @pytest.mark.slow
    @pytest.mark.integration
    def test_performance_under_load(self, rag_system):
        """부하 테스트"""
        import time

        # Given
        queries = ["쿼리1", "쿼리2", "쿼리3"]

        # When
        start_time = time.time()
        for query in queries:
            rag_system.search(query)
        elapsed = time.time() - start_time

        # Then
        assert elapsed < 10  # 10초 이내 완료
