"""
Test fixtures for RAG system
"""

import pytest
from pathlib import Path
import tempfile
import shutil

@pytest.fixture
def temp_dir():
    """임시 디렉토리 fixture"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

@pytest.fixture
def sample_pdf_content():
    """샘플 PDF 내용"""
    return """
    2024년 기안서
    작성자: 김철수
    제목: 장비 구매 요청
    내용: 방송 장비 구매를 요청합니다.
    금액: 5,000,000원
    """

@pytest.fixture
def sample_documents():
    """샘플 문서 리스트"""
    return [
        {
            'path': Path('doc1.pdf'),
            'content': '2024년 구매 기안서 내용',
            'metadata': {'date': '2024-01-01', 'author': '김철수'}
        },
        {
            'path': Path('doc2.pdf'),
            'content': '2023년 수리 보고서 내용',
            'metadata': {'date': '2023-12-01', 'author': '이영희'}
        }
    ]

@pytest.fixture
def mock_config():
    """테스트용 설정"""
    from rag_modules.core.config import RAGConfig, CacheConfig, ParallelConfig

    config = RAGConfig()
    config.cache = CacheConfig(max_size=10, ttl=60)
    config.parallel = ParallelConfig(max_workers=2)
    return config

@pytest.fixture
def mock_llm_response():
    """Mock LLM 응답"""
    return "이 문서는 2024년 장비 구매 기안서입니다. 총 금액은 500만원입니다."
