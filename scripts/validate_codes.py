#!/usr/bin/env python3
"""모델/부품 코드 검색 검증 스크립트

suites/model_codes.yaml 테스트 케이스 실행 및 메트릭 산출
- Hit@3, MRR@10, 인용률, P95 지연시간
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.rag.retrievers.hybrid import HybridRetriever

logger = get_logger(__name__)


def calculate_reciprocal_rank(results: List[Dict], expect_norm_code: str, db_conn) -> float:
    """Reciprocal Rank 계산 (norm_code 기준)

    Args:
        results: 검색 결과 리스트
        expect_norm_code: 기대하는 norm_code
        db_conn: DB 연결

    Returns:
        RR (1/rank 또는 0)
    """
    for rank, result in enumerate(results, start=1):
        filename = result.get("doc_id", "")

        # 해당 문서에 기대 norm_code가 있는지 확인
        cursor = db_conn.execute("""
            SELECT 1 FROM model_codes m
            JOIN documents d ON m.doc_id = d.id
            WHERE d.filename = ? AND m.norm_code = ?
            LIMIT 1
        """, (filename, expect_norm_code))

        if cursor.fetchone():
            return 1.0 / rank

    return 0.0


def validate_test_case(
    retriever: HybridRetriever,
    test_case: Dict[str, Any],
    db_conn,
    top_k: int = 10
) -> Dict[str, Any]:
    """단일 테스트 케이스 검증 (norm_code 기준)

    Args:
        retriever: HybridRetriever 인스턴스
        test_case: 테스트 케이스 (YAML에서 로드)
        db_conn: DB 연결
        top_k: 상위 K개 결과

    Returns:
        검증 결과 딕셔너리
    """
    test_id = test_case["id"]
    query = test_case["query"]
    expect_norm_code = test_case.get("expect_norm_code", test_case.get("expect_contains", ""))
    min_hits_at_3 = test_case.get("min_hits_at_3", 1)

    # 검색 실행 (지연시간 측정)
    start_time = time.time()
    results = retriever.search(query, top_k=top_k)
    latency_ms = (time.time() - start_time) * 1000

    # Hit@3 계산 (norm_code 기준)
    top3 = results[:3]
    hits_at_3 = 0
    for result in top3:
        filename = result.get("doc_id", "")
        cursor = db_conn.execute("""
            SELECT 1 FROM model_codes m
            JOIN documents d ON m.doc_id = d.id
            WHERE d.filename = ? AND m.norm_code = ?
            LIMIT 1
        """, (filename, expect_norm_code))
        if cursor.fetchone():
            hits_at_3 += 1

    # MRR@10 계산 (Reciprocal Rank)
    rr = calculate_reciprocal_rank(results, expect_norm_code, db_conn)

    # 인용 확인 (Top-10 내에 해당 norm_code 포함 여부)
    has_citation = False
    for result in results[:10]:
        filename = result.get("doc_id", "")
        cursor = db_conn.execute("""
            SELECT 1 FROM model_codes m
            JOIN documents d ON m.doc_id = d.id
            WHERE d.filename = ? AND m.norm_code = ?
            LIMIT 1
        """, (filename, expect_norm_code))
        if cursor.fetchone():
            has_citation = True
            break

    # PASS/FAIL 판정
    passed = hits_at_3 >= min_hits_at_3

    return {
        "test_id": test_id,
        "query": query,
        "hits_at_3": hits_at_3,
        "min_hits_at_3": min_hits_at_3,
        "rr": rr,
        "has_citation": has_citation,
        "latency_ms": latency_ms,
        "passed": passed,
        "results_count": len(results),
        "top3_docs": [r.get("doc_id", "")[:60] for r in top3]
    }


def run_validation_suite(suite_path: str = "suites/model_codes.yaml") -> Dict[str, Any]:
    """검증 스위트 실행

    Args:
        suite_path: YAML 테스트 스위트 경로

    Returns:
        전체 검증 결과
    """
    print("=" * 80)
    print("모델/부품 코드 검색 검증 스위트")
    print("=" * 80)

    # YAML 로드
    suite_file = Path(suite_path)
    if not suite_file.exists():
        print(f"❌ 테스트 스위트 파일 없음: {suite_path}")
        return {"error": "Suite file not found"}

    with open(suite_file, "r", encoding="utf-8") as f:
        suite = yaml.safe_load(f)

    test_cases = suite.get("test_cases", [])
    criteria = suite.get("performance_criteria", {})
    options = suite.get("validation_options", {})

    print(f"\n테스트 케이스: {len(test_cases)}개")
    print(f"성능 기준: Hit@3 ≥ {criteria.get('hit_at_3_min', 0.9)}, "
          f"MRR@10 ≥ {criteria.get('mrr_at_10_min', 0.8)}, "
          f"P95 < {criteria.get('p95_latency_max_ms', 5000)}ms")
    print()

    # Retriever 초기화
    retriever = HybridRetriever()

    # DB 연결
    import sqlite3
    db_conn = sqlite3.connect("metadata.db")

    # 테스트 실행
    results = []
    for idx, test_case in enumerate(test_cases, 1):
        print(f"[{idx}/{len(test_cases)}] {test_case['id']}: {test_case['description']}")
        result = validate_test_case(retriever, test_case, db_conn, top_k=options.get("top_k", 10))
        results.append(result)

        # 결과 출력
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"  {status} | Hits@3: {result['hits_at_3']}/{result['min_hits_at_3']}, "
              f"RR: {result['rr']:.3f}, Latency: {result['latency_ms']:.1f}ms")
        print(f"  Top 3: {result['top3_docs']}")
        print()

    # 집계 메트릭 계산
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    hit_at_3_rate = sum(r["hits_at_3"] >= 1 for r in results) / total if total > 0 else 0
    mrr_at_10 = sum(r["rr"] for r in results) / total if total > 0 else 0
    citation_rate = sum(1 for r in results if r["has_citation"]) / total if total > 0 else 0

    latencies = [r["latency_ms"] for r in results]
    latencies_sorted = sorted(latencies)
    p50_latency = latencies_sorted[int(len(latencies_sorted) * 0.5)] if latencies else 0
    p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies else 0

    # 기준 통과 여부
    criteria_passed = {
        "hit_at_3": hit_at_3_rate >= criteria.get("hit_at_3_min", 0.9),
        "mrr_at_10": mrr_at_10 >= criteria.get("mrr_at_10_min", 0.8),
        "citation_rate": citation_rate >= criteria.get("citation_rate_min", 1.0),
        "p95_latency": p95_latency < criteria.get("p95_latency_max_ms", 5000)
    }

    # 결과 요약 출력
    print("=" * 80)
    print("검증 결과 요약")
    print("=" * 80)
    print(f"테스트 케이스: {passed}/{total} PASS ({passed / total * 100:.1f}%)")
    print()
    print("성능 메트릭:")
    print(f"  Hit@3:         {hit_at_3_rate:.3f} "
          f"({'✅ PASS' if criteria_passed['hit_at_3'] else '❌ FAIL'})")
    print(f"  MRR@10:        {mrr_at_10:.3f} "
          f"({'✅ PASS' if criteria_passed['mrr_at_10'] else '❌ FAIL'})")
    print(f"  Citation Rate: {citation_rate:.3f} "
          f"({'✅ PASS' if criteria_passed['citation_rate'] else '❌ FAIL'})")
    print(f"  P50 Latency:   {p50_latency:.1f}ms")
    print(f"  P95 Latency:   {p95_latency:.1f}ms "
          f"({'✅ PASS' if criteria_passed['p95_latency'] else '❌ FAIL'})")
    print()

    all_passed = all(criteria_passed.values())
    if all_passed:
        print("✅ 전체 검증 통과")
    else:
        failed_criteria = [k for k, v in criteria_passed.items() if not v]
        print(f"❌ 검증 실패: {', '.join(failed_criteria)}")

    print("=" * 80)

    # DB 연결 종료
    db_conn.close()

    return {
        "total": total,
        "passed": passed,
        "hit_at_3_rate": hit_at_3_rate,
        "mrr_at_10": mrr_at_10,
        "citation_rate": citation_rate,
        "p50_latency_ms": p50_latency,
        "p95_latency_ms": p95_latency,
        "criteria_passed": criteria_passed,
        "all_passed": all_passed,
        "test_results": results
    }


if __name__ == "__main__":
    result = run_validation_suite()
    sys.exit(0 if result.get("all_passed", False) else 1)
