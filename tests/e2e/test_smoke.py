#!/usr/bin/env python3
"""
Smoke tests for AI-CHAT system.
Quick tests to verify basic functionality.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that core modules can be imported."""
    try:
        import app.data.metadata_db
        import app.rag.pipeline
        import app.rag.query_parser
        import app.rag.query_router
        print("✅ Core modules import successfully")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_database_connection():
    """Test database connectivity."""
    try:
        from app.data.metadata_db import MetadataDB

        db = MetadataDB()
        count = db.count_documents()

        assert count > 0, f"No documents in database (count={count})"
        assert count == 483, f"Unexpected document count: {count} (expected 483)"

        print(f"✅ Database connected: {count} documents")
        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_known_drafters():
    """Test that known drafters can be loaded."""
    try:
        from app.data.metadata_db import MetadataDB

        db = MetadataDB()
        drafters = db.list_unique_drafters()

        assert len(drafters) > 0, "No drafters found"
        assert len(drafters) == 11, f"Unexpected drafter count: {len(drafters)}"

        print(f"✅ Known drafters loaded: {len(drafters)} drafters")
        return True
    except Exception as e:
        print(f"❌ Drafter loading failed: {e}")
        return False


def test_query_parser():
    """Test query parsing functionality."""
    try:
        from app.data.metadata_db import MetadataDB
        from app.rag.query_parser import QueryParser

        db = MetadataDB()
        known_drafters = db.list_unique_drafters()
        parser = QueryParser(known_drafters)

        # Test cases
        test_cases = [
            ("2024년 문서", {"year": "2024", "drafter": None}),
            ("최새름이 작성한 문서", {"year": None, "drafter": "최새름"}),
            ("year:2023 drafter:남준수", {"year": "2023", "drafter": "남준수"}),
        ]

        for query, expected in test_cases:
            result = parser.parse_filters(query)
            assert result["year"] == expected["year"], f"Year mismatch for '{query}'"
            assert result["drafter"] == expected["drafter"], f"Drafter mismatch for '{query}'"

        print("✅ Query parser working correctly")
        return True
    except Exception as e:
        print(f"❌ Query parser test failed: {e}")
        return False


def test_query_router():
    """Test query routing functionality."""
    try:
        from app.rag.query_router import QueryMode, QueryRouter

        router = QueryRouter()

        # Test cases (LIST → SEARCH, COST_SUM → COST로 통합됨)
        test_cases = [
            ("문서 목록 보여줘", QueryMode.SEARCH),
            ("2024년 문서 찾아줘", QueryMode.SEARCH),
            ("비용 합계", QueryMode.COST),
        ]

        for query, expected_mode in test_cases:
            decision = router.classify_mode(query)
            assert decision.mode == expected_mode, f"Mode mismatch for '{query}': got {decision.mode}, expected {expected_mode}"

        print("✅ Query router working correctly")
        return True
    except Exception as e:
        print(f"❌ Query router test failed: {e}")
        return False


def test_retriever():
    """Test document retrieval."""
    try:
        from app.rag.retrievers.hybrid import HybridRetriever

        retriever = HybridRetriever()

        # Test search
        results = retriever.search("2024년 문서", top_k=5)

        assert isinstance(results, list), "Results should be a list"
        assert len(results) <= 5, f"Too many results: {len(results)}"

        if results:
            first = results[0]
            assert "doc_id" in first, "Missing doc_id in result"
            assert "snippet" in first, "Missing snippet in result"
            assert "meta" in first, "Missing meta in result"

        print(f"✅ Retriever working: {len(results)} results")
        return True
    except Exception as e:
        print(f"❌ Retriever test failed: {e}")
        return False


def test_pipeline_initialization():
    """Test RAG pipeline initialization."""
    try:
        from app.rag.pipeline import RAGPipeline

        start = time.time()
        pipeline = RAGPipeline()
        init_time = time.time() - start

        assert pipeline is not None, "Pipeline initialization failed"
        assert hasattr(pipeline, "answer"), "Pipeline missing answer method"
        assert hasattr(pipeline, "query_router"), "Pipeline missing query router"
        assert init_time < 5.0, f"Pipeline initialization too slow: {init_time:.2f}s"

        print(f"✅ Pipeline initialized in {init_time:.2f}s")
        return True
    except Exception as e:
        print(f"❌ Pipeline initialization failed: {e}")
        return False


def test_simple_query():
    """Test a simple query end-to-end."""
    try:
        from app.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()

        start = time.time()
        response = pipeline.answer("2024년 문서 목록")
        query_time = time.time() - start

        assert response is not None, "No response received"
        assert "text" in response, "Response missing text field"
        assert query_time < 30.0, f"Query too slow: {query_time:.2f}s"

        # Check if we got results
        status = response.get("status", {})
        found = status.get("found", False)
        count = status.get("retrieved_count", 0)

        print(f"✅ Query completed in {query_time:.2f}s: found={found}, count={count}")
        return True
    except Exception as e:
        print(f"❌ Query test failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("\n🧪 Running AI-CHAT Smoke Tests\n")
    print("=" * 50)

    tests = [
        ("Imports", test_imports),
        ("Database Connection", test_database_connection),
        ("Known Drafters", test_known_drafters),
        ("Query Parser", test_query_parser),
        ("Query Router", test_query_router),
        ("Retriever", test_retriever),
        ("Pipeline Init", test_pipeline_initialization),
        ("Simple Query", test_simple_query),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n📋 Testing: {name}")
        print("-" * 30)
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("📊 Test Summary\n")

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, passed_flag in results:
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\n🏆 Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All smoke tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
