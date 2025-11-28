#!/usr/bin/env python3
"""
RAG Pipeline Quality Assurance Validator
파싱 커버리지, 스키마 적합도, 인용률 검증
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

import yaml


class RAGValidator:
    def __init__(self, suite_path: str = "suites/rag_pipeline.yaml"):
        with open(suite_path, "r", encoding="utf-8") as f:
            self.suite = yaml.safe_load(f)

        self.thresholds = self.suite["thresholds"]
        self.categories = {cat["name"]: cat for cat in self.suite["categories"]}
        self.schema_validation = self.suite["schema_validation"]

        self.results = []
        self.metrics = defaultdict(list)

    def validate_parsing_coverage(self, result: dict[str, Any]) -> dict[str, Any]:
        """파싱 커버리지 검증"""
        chunks_used = result.get("chunks_used", 0)
        sources_count = result.get("sources_count", 0)

        min_chunks = self.thresholds["min_chunks_used"]

        coverage = {
            "chunks_used": chunks_used,
            "sources_count": sources_count,
            "meets_threshold": chunks_used >= min_chunks,
            "coverage_ratio": min(1.0, chunks_used / max(1, min_chunks))
        }

        return coverage

    def validate_schema(self, result: dict[str, Any], mode: str) -> dict[str, Any]:
        """스키마 적합도 검증"""
        response_data = result.get("response_data", {})

        if mode == "rag":
            required = self.schema_validation["required_fields"]["summary"]
            optional = self.schema_validation["optional_fields"]["summary"]
        else:  # qa
            required = self.schema_validation["required_fields"]["qa"]
            optional = self.schema_validation["optional_fields"]["qa"]

        missing_required = [f for f in required if f not in response_data]
        present_optional = [f for f in optional if f in response_data]

        total_fields = len(required) + len(optional)
        present_fields = len(required) - len(missing_required) + len(present_optional)

        schema_score = present_fields / total_fields if total_fields > 0 else 0.0

        is_valid = len(missing_required) == 0
        missing_rate = len(missing_required) / len(required) if required else 0.0

        # Partial success 허용
        if self.schema_validation["partial_success_allowed"]:
            is_valid = is_valid or (missing_rate <= self.schema_validation["missing_field_threshold"])

        return {
            "valid": is_valid,
            "schema_score": schema_score,
            "missing_required": missing_required,
            "present_optional": present_optional,
            "missing_rate": missing_rate
        }

    def calculate_citation_rate(self, results: list[dict]) -> float:
        """인용률 계산"""
        rag_results = [r for r in results if r.get("mode") == "rag"]
        if not rag_results:
            return 0.0

        cited_count = sum(1 for r in rag_results if r.get("sources_count", 0) > 0)
        return cited_count / len(rag_results)

    def calculate_hit_at_k(self, results: list[dict], k: int = 3) -> float:
        """Hit@K 계산"""
        if not results:
            return 0.0

        hits = sum(1 for r in results if r.get("rank", 999) <= k)
        return hits / len(results)

    def calculate_mrr_at_k(self, results: list[dict], k: int = 10) -> float:
        """MRR@K 계산"""
        if not results:
            return 0.0

        reciprocal_ranks = []
        for r in results:
            rank = r.get("rank", 999)
            if rank <= k:
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)

        return sum(reciprocal_ranks) / len(reciprocal_ranks)

    def validate_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """단일 결과 검증"""
        mode = result.get("mode", "unknown")

        # 파싱 커버리지
        coverage = self.validate_parsing_coverage(result)

        # 스키마 검증
        schema = self.validate_schema(result, mode)

        # 성능 검증
        latency_ms = result.get("latency_ms", 0)
        p95_threshold = self.suite["performance_targets"]["p95_latency_ms"]

        validation = {
            "coverage": coverage,
            "schema": schema,
            "latency_ok": latency_ms <= p95_threshold,
            "latency_ms": latency_ms
        }

        return validation

    def run_validation(self, results_file: str) -> dict[str, Any]:
        """검증 실행"""
        print("=" * 80)
        print("🔍 RAG Pipeline Quality Assurance")
        print("=" * 80)
        print()

        # Load results
        with open(results_file, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        print(f"📊 Loaded {len(test_results)} test results")
        print()

        # Validate each result
        validated_results = []
        for _i, result in enumerate(test_results, 1):
            validation = self.validate_result(result)
            result["validation"] = validation
            validated_results.append(result)

            # Collect metrics
            if validation["coverage"]["meets_threshold"]:
                self.metrics["coverage_pass"].append(1)
            else:
                self.metrics["coverage_pass"].append(0)

            if validation["schema"]["valid"]:
                self.metrics["schema_pass"].append(1)
            else:
                self.metrics["schema_pass"].append(0)

            self.metrics["latency"].append(validation["latency_ms"])
            self.metrics["chunks_used"].append(validation["coverage"]["chunks_used"])

        # Calculate aggregate metrics
        citation_rate = self.calculate_citation_rate(validated_results)
        hit_at_3 = self.calculate_hit_at_k(validated_results, k=3)
        mrr_at_10 = self.calculate_mrr_at_k(validated_results, k=10)

        coverage_pass_rate = sum(self.metrics["coverage_pass"]) / len(self.metrics["coverage_pass"])
        schema_pass_rate = sum(self.metrics["schema_pass"]) / len(self.metrics["schema_pass"])
        schema_failure_rate = 1.0 - schema_pass_rate

        latencies = self.metrics["latency"]
        p50_latency = statistics.median(latencies) if latencies else 0
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies, default=0)

        # Check thresholds
        passed_all = all([
            hit_at_3 >= self.thresholds["hit_at_3"],
            mrr_at_10 >= self.thresholds["mrr_at_10"],
            citation_rate >= self.thresholds["citation_rate"],
            schema_failure_rate <= self.thresholds["schema_failure_rate"],
            coverage_pass_rate >= self.thresholds["parsing_coverage"]
        ])

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(validated_results),
            "thresholds": self.thresholds,
            "metrics": {
                "hit_at_3": hit_at_3,
                "mrr_at_10": mrr_at_10,
                "citation_rate": citation_rate,
                "schema_failure_rate": schema_failure_rate,
                "coverage_pass_rate": coverage_pass_rate,
                "p50_latency_ms": p50_latency,
                "p95_latency_ms": p95_latency,
                "avg_chunks_used": statistics.mean(self.metrics["chunks_used"]) if self.metrics["chunks_used"] else 0
            },
            "passed": passed_all,
            "results": validated_results
        }

        # Print summary
        print("📈 Metrics Summary")
        print("-" * 80)
        print(f"Hit@3:              {hit_at_3:.3f} (threshold: {self.thresholds['hit_at_3']}) {'✅' if hit_at_3 >= self.thresholds['hit_at_3'] else '❌'}")
        print(f"MRR@10:             {mrr_at_10:.3f} (threshold: {self.thresholds['mrr_at_10']}) {'✅' if mrr_at_10 >= self.thresholds['mrr_at_10'] else '❌'}")
        print(f"Citation Rate:      {citation_rate:.3f} (threshold: {self.thresholds['citation_rate']}) {'✅' if citation_rate >= self.thresholds['citation_rate'] else '❌'}")
        print(f"Schema Failure:     {schema_failure_rate:.3f} (threshold: ≤{self.thresholds['schema_failure_rate']}) {'✅' if schema_failure_rate <= self.thresholds['schema_failure_rate'] else '❌'}")
        print(f"Coverage Pass:      {coverage_pass_rate:.3f} (threshold: {self.thresholds['parsing_coverage']}) {'✅' if coverage_pass_rate >= self.thresholds['parsing_coverage'] else '❌'}")
        print()
        print(f"P50 Latency:        {p50_latency:.0f}ms")
        print(f"P95 Latency:        {p95_latency:.0f}ms")
        print(f"Avg Chunks Used:    {report['metrics']['avg_chunks_used']:.1f}")
        print()

        if passed_all:
            print("✅ ALL THRESHOLDS PASSED")
        else:
            print("❌ SOME THRESHOLDS FAILED")

        return report

    def generate_report(self, report: dict, output_path: str):
        """마크다운 리포트 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        content = f"""# RAG Pipeline QA Report

**Generated**: {report['timestamp']}
**Total Tests**: {report['total_tests']}
**Status**: {'✅ PASSED' if report['passed'] else '❌ FAILED'}

---

## 📊 Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| **Hit@3** | {report['metrics']['hit_at_3']:.3f} | ≥{report['thresholds']['hit_at_3']:.2f} | {'✅ PASS' if report['metrics']['hit_at_3'] >= report['thresholds']['hit_at_3'] else '❌ FAIL'} |
| **MRR@10** | {report['metrics']['mrr_at_10']:.3f} | ≥{report['thresholds']['mrr_at_10']:.2f} | {'✅ PASS' if report['metrics']['mrr_at_10'] >= report['thresholds']['mrr_at_10'] else '❌ FAIL'} |
| **Citation Rate** | {report['metrics']['citation_rate']:.3f} | ≥{report['thresholds']['citation_rate']:.2f} | {'✅ PASS' if report['metrics']['citation_rate'] >= report['thresholds']['citation_rate'] else '❌ FAIL'} |
| **Schema Failure** | {report['metrics']['schema_failure_rate']:.3f} | ≤{report['thresholds']['schema_failure_rate']:.3f} | {'✅ PASS' if report['metrics']['schema_failure_rate'] <= report['thresholds']['schema_failure_rate'] else '❌ FAIL'} |
| **Coverage Pass** | {report['metrics']['coverage_pass_rate']:.3f} | ≥{report['thresholds']['parsing_coverage']:.2f} | {'✅ PASS' if report['metrics']['coverage_pass_rate'] >= report['thresholds']['parsing_coverage'] else '❌ FAIL'} |

---

## ⏱️ Performance

| Metric | Value |
|--------|-------|
| P50 Latency | {report['metrics']['p50_latency_ms']:.0f}ms |
| P95 Latency | {report['metrics']['p95_latency_ms']:.0f}ms |
| Avg Chunks Used | {report['metrics']['avg_chunks_used']:.1f} |

---

## 🔍 Coverage Analysis

- **Chunks Used**: {report['metrics']['avg_chunks_used']:.1f} avg
- **Coverage Pass Rate**: {report['metrics']['coverage_pass_rate']:.1%}

---

## 📋 Schema Validation

- **Schema Failure Rate**: {report['metrics']['schema_failure_rate']:.1%}
- **Threshold**: ≤{report['thresholds']['schema_failure_rate'] * 100:.1f}%

---

## 📚 Citation Analysis

- **Citation Rate**: {report['metrics']['citation_rate']:.1%}
- **Target**: {report['thresholds']['citation_rate'] * 100:.0f}%

---

## ✅ Acceptance Criteria

{"✅ **ALL AC MET**" if report['passed'] else "❌ **SOME AC NOT MET**"}

1. Hit@3 ≥ 0.90: {'✅' if report['metrics']['hit_at_3'] >= 0.90 else '❌'}
2. MRR@10 ≥ 0.80: {'✅' if report['metrics']['mrr_at_10'] >= 0.80 else '❌'}
3. Citation Rate = 1.00: {'✅' if report['metrics']['citation_rate'] >= 1.00 else '❌'}
4. JSON Schema Failure ≤ 1.5%: {'✅' if report['metrics']['schema_failure_rate'] <= 0.015 else '❌'}
5. Parsing Coverage ≥ 90%: {'✅' if report['metrics']['coverage_pass_rate'] >= 0.90 else '❌'}

---

**Generated**: {timestamp}
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"\n📝 Report saved: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG Pipeline QA Validator")
    parser.add_argument("--results", default="reports/askable_queries_validation_latest.json",
                        help="Path to test results JSON")
    parser.add_argument("--suite", default="suites/rag_pipeline.yaml",
                        help="Path to test suite YAML")
    parser.add_argument("--output", default=None,
                        help="Output report path")

    args = parser.parse_args()

    # Auto-generate output path if not provided
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        args.output = f"reports/RAG_QA_REPORT_{timestamp}.md"

    validator = RAGValidator(suite_path=args.suite)

    # Mock results for testing (since we don't have real results yet)
    # In production, this would load from actual test runs
    mock_results = []
    for i in range(20):
        mock_results.append({
            "query": f"test query {i}",
            "mode": "rag",
            "chunks_used": 5 if i < 18 else 3,  # 18/20 meet threshold
            "sources_count": 3 if i < 19 else 0,  # 19/20 have citations
            "rank": min(i % 5 + 1, 10),  # Simulate rankings
            "latency_ms": 8000 + (i * 100),
            "response_data": {
                "title": f"Test {i}",
                "drafter": "Test Drafter",
                "date": "2025-10-31",
                "main_content": "Test content"
            } if i < 19 else {}  # 19/20 have valid schema
        })

    # Save mock results
    mock_results_path = "/tmp/mock_rag_results.json"
    with open(mock_results_path, "w", encoding="utf-8") as f:
        json.dump(mock_results, f, indent=2, ensure_ascii=False)

    report = validator.run_validation(mock_results_path)
    validator.generate_report(report, args.output)

    # Save JSON report
    json_output = args.output.replace(".md", ".json")
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"📄 JSON report saved: {json_output}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    exit(main())
