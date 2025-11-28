#!/usr/bin/env python3
"""
20 runtime scenarios for coverage testing.
Includes query, response, and error cases.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.pipeline import RAGPipeline
from app.data.metadata_db import MetadataDB
from app.rag.query_parser import QueryParser
from app.rag.query_router import QueryRouter


class ScenarioRunner:
    """Run 20 diverse scenarios for runtime coverage."""

    def __init__(self):
        self.pipeline = RAGPipeline()
        self.db = MetadataDB()
        self.results = []

    def run_all(self):
        """Execute all 20 scenarios."""

        scenarios = [
            # Basic queries (5)
            ("2024년 문서 목록", "LIST"),
            ("2023년 최새름이 작성한 문서", "LIST"),
            ("year:2024 drafter:남준수", "QA"),
            ("비용 합계 알려줘", "COST_SUM"),
            ("문서 찾아줘", "LIST"),

            # Complex queries (5)
            ("2024년 11월 이후 작성된 보고서", "LIST"),
            ("방송 장비 관련 문서 검색", "QA"),
            ("최근 3개월 문서 요약", "SUMMARY"),
            ("2024-12-16_방송_프로그램_제작용_건전지_소모품_구매의_건.pdf 내용", "PREVIEW"),
            ("김철수가 작성한 문서", "LIST"),  # Non-existent drafter

            # Error cases (5)
            ("", "QA"),  # Empty query
            ("year:9999", "QA"),  # Invalid year
            ("drafter:!!!@@@", "QA"),  # Invalid drafter
            ("a" * 1000, "QA"),  # Very long query
            ("SELECT * FROM documents", "QA"),  # SQL injection attempt

            # Edge cases (5)
            ("문서", "LIST"),  # Stopword only
            ("2020년 문서", "LIST"),  # Year with no documents
            ("년", "QA"),  # Partial year
            ("최 새 름", "LIST"),  # Name with spaces
            ("YEAR:2024 DRAFTER:남준수", "QA"),  # Uppercase tokens
        ]

        print(f"🧪 Running {len(scenarios)} scenarios for coverage...\n")

        for i, (query, expected_mode) in enumerate(scenarios, 1):
            print(f"[{i:2d}/20] Testing: {query[:50]}...")

            try:
                start = time.time()

                # Test routing
                router = QueryRouter()
                mode = router.classify_mode(query)

                # Test parsing
                parser = QueryParser(self.db.list_unique_drafters())
                filters = parser.parse_filters(query)

                # Test pipeline
                response = self.pipeline.answer(query)

                elapsed = time.time() - start

                success = response is not None and "text" in response
                self.results.append({
                    "scenario": i,
                    "query": query[:50],
                    "expected_mode": expected_mode,
                    "actual_mode": mode.value if mode else None,
                    "filters": filters,
                    "success": success,
                    "time": elapsed,
                    "error": None
                })

                status = "✅" if success else "❌"
                print(f"  {status} Mode: {mode.value if mode else 'None'}, "
                      f"Time: {elapsed:.2f}s\n")

            except Exception as e:
                self.results.append({
                    "scenario": i,
                    "query": query[:50],
                    "expected_mode": expected_mode,
                    "actual_mode": None,
                    "filters": None,
                    "success": False,
                    "time": 0,
                    "error": str(e)
                })
                print(f"  ❌ Error: {e}\n")

        return self.results

    def generate_report(self):
        """Generate coverage report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])

        report = f"""
# Runtime Coverage Report

## Summary
- Total Scenarios: {total}
- Passed: {passed}
- Failed: {total - passed}
- Success Rate: {passed/total*100:.1f}%

## Detailed Results
"""

        for r in self.results:
            status = "✅" if r["success"] else "❌"
            report += f"\n### Scenario {r['scenario']}: {status}\n"
            report += f"- Query: `{r['query']}`\n"
            report += f"- Expected Mode: {r['expected_mode']}\n"
            report += f"- Actual Mode: {r['actual_mode']}\n"
            report += f"- Filters: {r['filters']}\n"
            report += f"- Time: {r['time']:.3f}s\n"
            if r['error']:
                report += f"- Error: {r['error']}\n"

        return report


def main():
    """Run all scenarios and generate report."""
    runner = ScenarioRunner()
    results = runner.run_all()

    # Generate report
    report = runner.generate_report()

    # Save report
    with open("reports/runtime_coverage.md", "w") as f:
        f.write(report)

    print("\n" + "=" * 50)
    print("📊 Coverage Report Summary")
    print("=" * 50)

    total = len(results)
    passed = sum(1 for r in results if r["success"])
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {passed/total*100:.1f}%")

    print(f"\n✅ Report saved to reports/runtime_coverage.md")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())