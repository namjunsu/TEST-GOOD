#!/usr/bin/env python3
"""
RAG 회귀 벤치마크

골든 셋 기반 성능 측정:
- Hit@k (정확도)
- MRR (Mean Reciprocal Rank)
- P50/P95 Latency (성능)
- 실패율

Usage:
    python scripts/bench_rag.py
    python scripts/bench_rag.py --golden-set data/golden_set.json
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class BenchResult:
    """벤치마크 결과"""
    query: str
    expected_docs: list[str]
    retrieved_docs: list[str]
    hit: bool
    reciprocal_rank: float
    latency: float
    success: bool
    error: Optional[str] = None


@dataclass
class BenchSummary:
    """벤치마크 요약"""
    total: int = 0
    hits: int = 0
    success: int = 0
    failures: int = 0
    latencies: list[float] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)

    def add_result(self, result: BenchResult):
        """결과 추가"""
        self.total += 1
        if result.success:
            self.success += 1
            if result.hit:
                self.hits += 1
            self.latencies.append(result.latency)
            self.reciprocal_ranks.append(result.reciprocal_rank)
        else:
            self.failures += 1

    def compute(self) -> dict[str, Any]:
        """메트릭 계산"""
        if not self.latencies:
            return {
                "error": "No successful queries",
                "total": self.total,
                "failures": self.failures,
            }

        sorted_lat = sorted(self.latencies)
        n = len(sorted_lat)

        return {
            "total_queries": self.total,
            "successes": self.success,
            "failures": self.failures,
            "success_rate": self.success / self.total if self.total > 0 else 0,
            "hit_at_5": self.hits / self.success if self.success > 0 else 0,
            "mrr": sum(self.reciprocal_ranks) / len(self.reciprocal_ranks) if self.reciprocal_ranks else 0,
            "latency_p50": sorted_lat[int(n * 0.5)] if n > 0 else 0,
            "latency_p95": sorted_lat[int(n * 0.95)] if n > 0 else 0,
            "latency_mean": sum(sorted_lat) / n if n > 0 else 0,
        }


# 골든 셋 (예시 - 실제로는 파일에서 로드)
DEFAULT_GOLDEN_SET = [
    {
        "query": "2024년 예산은 얼마인가요?",
        "expected_docs": ["budget_2024.pdf", "finance_report_2024.pdf"],
    },
    {
        "query": "신규 채용 계획이 있나요?",
        "expected_docs": ["hr_plan_2024.pdf", "recruitment_2024.pdf"],
    },
    {
        "query": "올해 주요 프로젝트는?",
        "expected_docs": ["project_plan_2024.pdf", "annual_goals_2024.pdf"],
    },
    # 실제로는 30~50개 질문
]


def load_golden_set(filepath: Optional[Path] = None) -> list[dict[str, Any]]:
    """골든 셋 로드

    Args:
        filepath: 골든 셋 JSON 파일 경로

    Returns:
        List of queries with expected docs
    """
    if filepath and filepath.exists():
        with Path(filepath).open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        print(f"⚠️  골든 셋 파일 없음, 기본값 사용: {len(DEFAULT_GOLDEN_SET)}개")
        return DEFAULT_GOLDEN_SET


def bench_query(pipeline, query: str, expected_docs: list[str], top_k: int = 5) -> BenchResult:
    """단일 질의 벤치마크

    Args:
        pipeline: RAG 파이프라인
        query: 질문
        expected_docs: 예상 문서 ID 목록
        top_k: 검색할 문서 수

    Returns:
        BenchResult
    """
    start = time.time()
    success = False
    error = None
    retrieved_docs = []
    hit = False
    reciprocal_rank = 0.0

    try:
        # RAG 파이프라인 실행
        response = pipeline.answer(query, top_k=top_k)
        retrieved_docs = [ev.get("doc_id", "") for ev in response.evidence]
        success = True

        # Hit@k 계산
        expected_set = set(expected_docs)
        retrieved_set = set(retrieved_docs)
        hit = bool(expected_set & retrieved_set)

        # MRR 계산 (첫 번째 정답 문서의 순위)
        for i, doc_id in enumerate(retrieved_docs, 1):
            if doc_id in expected_set:
                reciprocal_rank = 1.0 / i
                break

    except Exception as e:
        error = str(e)

    latency = time.time() - start

    return BenchResult(
        query=query,
        expected_docs=expected_docs,
        retrieved_docs=retrieved_docs,
        hit=hit,
        reciprocal_rank=reciprocal_rank,
        latency=latency,
        success=success,
        error=error,
    )


def run_benchmark(golden_set_path: Optional[Path] = None, top_k: int = 5) -> BenchSummary:
    """벤치마크 실행

    Args:
        golden_set_path: 골든 셋 파일 경로
        top_k: 검색할 문서 수

    Returns:
        BenchSummary
    """
    print("=" * 60)
    print("  RAG 회귀 벤치마크")
    print("=" * 60)
    print()

    # 골든 셋 로드
    golden_set = load_golden_set(golden_set_path)
    print(f"📊 골든 셋: {len(golden_set)}개 질문")
    print()

    # RAG 파이프라인 초기화
    print("🔧 RAG 파이프라인 초기화 중...")

    try:
        # 새 구조 (app/rag/pipeline.py)
        from app.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()
        print("✅ app.rag.pipeline 로드 완료")

    except ImportError as e:
        print(f"❌ RAG 파이프라인을 찾을 수 없습니다: {e}")
        sys.exit(1)

    print()

    # 벤치마크 실행
    summary = BenchSummary()

    for i, item in enumerate(golden_set, 1):
        query = item["query"]
        expected = item["expected_docs"]

        print(f"[{i}/{len(golden_set)}] {query[:50]}...")

        result = bench_query(pipeline, query, expected, top_k)
        summary.add_result(result)

        if result.success:
            status = "✅ HIT" if result.hit else "❌ MISS"
            print(f"  {status} | {result.latency:.2f}s | RR={result.reciprocal_rank:.3f}")
        else:
            print(f"  ❌ FAIL: {result.error}")

        print()

    # 결과 요약
    print("=" * 60)
    print("  벤치마크 결과")
    print("=" * 60)

    metrics = summary.compute()

    if "error" in metrics:
        print(f"❌ {metrics['error']}")
        return summary

    print(f"총 질문: {metrics['total_queries']}")
    print(f"성공: {metrics['successes']} ({metrics['success_rate']:.1%})")
    print(f"실패: {metrics['failures']}")
    print()
    print(f"Hit@{top_k}: {metrics['hit_at_5']:.1%}")
    print(f"MRR: {metrics['mrr']:.3f}")
    print()
    print(f"Latency P50: {metrics['latency_p50']:.2f}s")
    print(f"Latency P95: {metrics['latency_p95']:.2f}s")
    print(f"Latency Mean: {metrics['latency_mean']:.2f}s")
    print("=" * 60)

    # 결과 저장
    output_path = Path("var/log/bench_metrics.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Path(output_path).open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 결과 저장: {output_path}")

    return summary


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="RAG 회귀 벤치마크")
    parser.add_argument(
        "--golden-set",
        type=Path,
        help="골든 셋 JSON 파일 경로",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="검색할 문서 수 (기본: 5)",
    )

    args = parser.parse_args()

    try:
        run_benchmark(args.golden_set, args.top_k)
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자 중단")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
