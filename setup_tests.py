#!/usr/bin/env python3
"""
전문적인 테스트 시스템 구축
pytest + coverage + mock 활용
"""

import os
from pathlib import Path

def create_test_structure():
    """테스트 구조 생성"""

    print("="*60)
    print("🧪 전문적인 테스트 시스템 구축")
    print("="*60)

    # 테스트 디렉토리 구조
    test_dirs = [
        'tests',
        'tests/unit',
        'tests/integration',
        'tests/fixtures',
        'tests/mocks'
    ]

    for dir_path in test_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        init_file = Path(dir_path) / '__init__.py'
        init_file.touch()

    print("✅ 테스트 디렉토리 구조 생성 완료")

def create_pytest_config():
    """pytest 설정 파일 생성"""

    pytest_ini = """[tool.pytest.ini_options]
minversion = "6.0"
addopts = [
    "-ra",
    "-q",
    "--strict-markers",
    "--cov=rag_modules",
    "--cov-report=html",
    "--cov-report=term-missing",
    "--cov-fail-under=80"
]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests"
]
"""

    with open('pyproject.toml', 'w') as f:
        f.write(pytest_ini)

    # pytest.ini 대체 버전
    pytest_ini_alt = """[pytest]
minversion = 6.0
addopts = -ra -q --strict-markers --cov=rag_modules --cov-report=html --cov-report=term-missing
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*

markers =
    slow: marks tests as slow
    integration: integration tests
    unit: unit tests
"""

    with open('pytest.ini', 'w') as f:
        f.write(pytest_ini_alt)

    print("✅ pytest 설정 파일 생성 완료")

def create_test_fixtures():
    """테스트 fixtures 생성"""

    fixtures_code = '''"""
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
'''

    with open('tests/fixtures/conftest.py', 'w') as f:
        f.write(fixtures_code)

    print("✅ 테스트 fixtures 생성 완료")

def create_unit_tests():
    """단위 테스트 생성"""

    # 1. Cache Manager 테스트
    cache_test = '''"""
Unit tests for Cache Manager
"""

import pytest
import time
from unittest.mock import Mock, patch
from rag_modules.cache.manager import CacheManager
from rag_modules.core.config import CacheConfig

class TestCacheManager:
    """CacheManager 단위 테스트"""

    @pytest.fixture
    def cache_manager(self):
        """캐시 매니저 fixture"""
        config = CacheConfig(max_size=3, ttl=1)
        return CacheManager(config)

    def test_cache_set_and_get(self, cache_manager):
        """캐시 저장 및 조회 테스트"""
        # Given
        key = "test_key"
        value = "test_value"

        # When
        cache_manager.set(key, value)
        result = cache_manager.get(key)

        # Then
        assert result == value

    def test_cache_lru_eviction(self, cache_manager):
        """LRU 캐시 제거 테스트"""
        # Given
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")
        cache_manager.set("key3", "value3")

        # When - 캐시 크기 초과
        cache_manager.set("key4", "value4")

        # Then - 가장 오래된 항목 제거됨
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key4") == "value4"

    def test_cache_ttl_expiration(self, cache_manager):
        """TTL 만료 테스트"""
        # Given
        cache_manager.set("key", "value")

        # When - TTL 만료 대기
        time.sleep(1.1)

        # Then
        assert cache_manager.get("key") is None

    def test_cache_stats(self, cache_manager):
        """캐시 통계 테스트"""
        # Given
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        # When
        stats = cache_manager.stats()

        # Then
        assert stats['size'] == 2
        assert stats['max_size'] == 3
        assert stats['ttl'] == 1
        assert 0 <= stats['hit_rate'] <= 1

    @pytest.mark.parametrize("key,value", [
        ("string_key", "string_value"),
        ("int_key", 12345),
        ("dict_key", {"nested": "value"}),
        ("list_key", [1, 2, 3])
    ])
    def test_cache_various_types(self, cache_manager, key, value):
        """다양한 타입 캐싱 테스트"""
        cache_manager.set(key, value)
        assert cache_manager.get(key) == value
'''

    # 2. Document Processor 테스트
    doc_processor_test = '''"""
Unit tests for Document Processor
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from rag_modules.document.processor import DocumentProcessor
from rag_modules.core.exceptions import PDFExtractionException

class TestDocumentProcessor:
    """DocumentProcessor 단위 테스트"""

    @pytest.fixture
    def processor(self):
        """프로세서 fixture"""
        return DocumentProcessor()

    def test_supported_formats(self, processor):
        """지원 포맷 확인 테스트"""
        assert '.pdf' in processor.supported_formats
        assert '.txt' in processor.supported_formats
        assert '.docx' in processor.supported_formats

    @patch('builtins.open', new_callable=mock_open, read_data='Test content')
    def test_extract_txt_text(self, mock_file, processor):
        """TXT 텍스트 추출 테스트"""
        # When
        result = processor._extract_txt_text(Path('test.txt'))

        # Then
        assert result == 'Test content'
        mock_file.assert_called_once_with(Path('test.txt'), 'r', encoding='utf-8')

    @patch('pdfplumber.open')
    def test_extract_pdf_text_success(self, mock_pdf, processor):
        """PDF 텍스트 추출 성공 테스트"""
        # Given
        mock_page = Mock()
        mock_page.extract_text.return_value = "Page content"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        # When
        result = processor._extract_pdf_text(Path('test.pdf'))

        # Then
        assert result == "Page content"

    @patch('pdfplumber.open')
    def test_extract_pdf_text_failure(self, mock_pdf, processor):
        """PDF 텍스트 추출 실패 테스트"""
        # Given
        mock_pdf.side_effect = Exception("PDF error")

        # When & Then
        with pytest.raises(PDFExtractionException):
            processor._extract_pdf_text(Path('test.pdf'))

    def test_extract_unsupported_format(self, processor):
        """지원하지 않는 포맷 테스트"""
        with pytest.raises(PDFExtractionException) as exc:
            processor.extract_text(Path('test.xyz'))
        assert "Unsupported format" in str(exc.value)
'''

    # 3. Search Engine 테스트
    search_engine_test = '''"""
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
'''

    # 파일 저장
    with open('tests/unit/test_cache_manager.py', 'w') as f:
        f.write(cache_test)

    with open('tests/unit/test_document_processor.py', 'w') as f:
        f.write(doc_processor_test)

    with open('tests/unit/test_search_engine.py', 'w') as f:
        f.write(search_engine_test)

    print("✅ 단위 테스트 생성 완료")

def create_integration_tests():
    """통합 테스트 생성"""

    integration_test = '''"""
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
'''

    with open('tests/integration/test_rag_integration.py', 'w') as f:
        f.write(integration_test)

    print("✅ 통합 테스트 생성 완료")

def create_test_runner():
    """테스트 실행 스크립트 생성"""

    runner_script = '''#!/usr/bin/env python3
"""
테스트 실행 스크립트
"""

import sys
import subprocess

def run_tests():
    """테스트 실행"""

    print("="*60)
    print("🧪 테스트 실행")
    print("="*60)

    commands = [
        # 단위 테스트
        ["pytest", "tests/unit", "-v", "--tb=short"],

        # 통합 테스트
        ["pytest", "tests/integration", "-v", "-m", "integration"],

        # 커버리지 리포트
        ["pytest", "--cov=rag_modules", "--cov-report=term-missing"],

        # HTML 리포트 생성
        ["pytest", "--cov=rag_modules", "--cov-report=html"]
    ]

    for cmd in commands:
        print(f"\\n실행: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ 테스트 실패: {result.stderr}")
        else:
            print(f"✅ 테스트 통과")

    print("\\n📊 커버리지 리포트: htmlcov/index.html")

if __name__ == "__main__":
    run_tests()
'''

    with open('run_tests.py', 'w') as f:
        f.write(runner_script)

    os.chmod('run_tests.py', 0o755)

    print("✅ 테스트 실행 스크립트 생성 완료")

def create_requirements_test():
    """테스트 requirements 생성"""

    requirements = """# Testing requirements
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
pytest-asyncio>=0.21.0
pytest-timeout>=2.1.0
pytest-xdist>=3.0.0  # 병렬 테스트 실행
coverage>=7.0.0
mock>=5.0.0
faker>=20.0.0  # 테스트 데이터 생성
hypothesis>=6.0.0  # Property-based testing
"""

    with open('requirements-test.txt', 'w') as f:
        f.write(requirements)

    print("✅ 테스트 requirements 생성 완료")

def main():
    """메인 실행 함수"""

    # 1. 테스트 구조 생성
    create_test_structure()

    # 2. pytest 설정
    create_pytest_config()

    # 3. Fixtures 생성
    create_test_fixtures()

    # 4. 단위 테스트 생성
    create_unit_tests()

    # 5. 통합 테스트 생성
    create_integration_tests()

    # 6. 테스트 실행 스크립트
    create_test_runner()

    # 7. Requirements 생성
    create_requirements_test()

    print("\n" + "="*60)
    print("✅ 전문적인 테스트 시스템 구축 완료!")
    print("="*60)

    print("\n📋 생성된 테스트:")
    print("  • 단위 테스트: 3개 모듈")
    print("  • 통합 테스트: 1개 스위트")
    print("  • 테스트 fixtures: 5개")
    print("  • 커버리지 목표: 80%")

    print("\n🚀 테스트 실행 방법:")
    print("  python3 run_tests.py")
    print("  또는")
    print("  pytest -v")

    print("\n🏆 최고의 개발자가 만든 완벽한 테스트 시스템!")

if __name__ == "__main__":
    main()