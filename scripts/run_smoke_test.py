#!/usr/bin/env python3
"""
E2E 스모크 테스트: Evidence 출력 및 검색 정확도 검증
"""

import sys
import time
from pathlib import Path

# 테스트 질의 정의
TEST_QUERIES = [
    {
        "query": "2019년 ENG 카메라 수리 내역을 알려줘",
        "target_doc_id": "2019-01-30_ENG_카메라_수리_신청서.pdf",
        "expected_keywords": ["ENG", "카메라", "수리"],
    },
    {
        "query": "트라이포드 발판 수리 건이 있었나?",
        "target_doc_id": "2019-01-14_카메라_트라이포트_발판_수리_건.pdf",
        "expected_keywords": ["트라이포드", "발판"],
    },
    {
        "query": "무선 마이크 전원 스위치 고장 수리한 적 있어?",
        "target_doc_id": "2017-09-05_무선_마이크_전원_스위치_수리_건.pdf",
        "expected_keywords": ["무선", "마이크", "전원"],
    },
    {
        "query": "2020년 3월에 스튜디오 지미짚 수리 건 찾아줘",
        "target_doc_id": "2020-03-11_영상카메라팀_스튜디오_지미짚_수리.pdf",
        "expected_keywords": ["스튜디오", "지미짚", "2020"],
    },
    {
        "query": "LED조명 수리 관련 문서 검색",
        "target_doc_id": "2019-05-10_영상취재팀_LED조명_수리_건.pdf",
        "expected_keywords": ["LED", "조명"],
    }
]


def run_test(pipeline, query_info):
    """단일 테스트 실행

    Args:
        pipeline: RAGPipeline 인스턴스
        query_info: 테스트 질의 정보 dict

    Returns:
        dict: 테스트 결과
    """
    query = query_info["query"]
    expected_keywords = query_info["expected_keywords"]

    # 시간 측정 시작
    t0 = time.perf_counter()

    # 질의 실행 (운영값: top_k=3)
    result = pipeline.answer(query, top_k=3)

    # 시간 측정 종료
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # Evidence 추출
    evidence = result.get("evidence", [])
    evidence_count = len(evidence)

    # Evidence 샘플
    if evidence:
        ev = evidence[0]
        doc_id = ev.get("doc_id", "")
        page = ev.get("page", 1)
        snippet = ev.get("snippet", "")[:80]
        evidence_sample = f"{doc_id}:{page} | {snippet}"
    else:
        evidence_sample = "-"

    # 응답 텍스트
    response_text = result.get("text", "")

    # Pass/Fail 판정
    # 조건 1: evidence ≥ 1
    # 조건 2: text에 expected_keywords 중 ≥1개 포함
    has_evidence = evidence_count >= 1
    has_keyword = any(kw in response_text for kw in expected_keywords)
    passed = has_evidence and has_keyword

    return {
        "query": query,
        "elapsed_ms": elapsed_ms,
        "evidence_count": evidence_count,
        "evidence_sample": evidence_sample,
        "response_text": response_text,
        "has_evidence": has_evidence,
        "has_keyword": has_keyword,
        "passed": passed,
        "target_doc_id": query_info["target_doc_id"],
        "expected_keywords": expected_keywords,
    }


def main():
    """메인 함수"""
    print("=" * 140)
    print("E2E 스모크 테스트: Evidence 출력 및 검색 정확도 검증")
    print("=" * 140)

    # RAGPipeline 초기화
    print("\n[1] RAGPipeline 초기화 중...")
    try:
        from app.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        print("✓ Pipeline 초기화 완료")

        # Warmup
        print("\n[2] Warmup 실행 중...")
        pipeline.warmup()
        print("✓ Warmup 완료")

    except Exception as e:
        print(f"✗ Pipeline 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 테스트 실행
    print(f"\n[3] 테스트 질의 {len(TEST_QUERIES)}건 실행 중...")
    print("=" * 140)

    results = []
    for i, query_info in enumerate(TEST_QUERIES, 1):
        print(f"\n질의 {i}/{len(TEST_QUERIES)}: {query_info['query']}")
        try:
            result = run_test(pipeline, query_info)
            results.append(result)

            status = "✓ PASS" if result["passed"] else "✗ FAIL"
            print(f"  {status} | {result['elapsed_ms']}ms | Evidence: {result['evidence_count']}건")

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "query": query_info["query"],
                "elapsed_ms": 0,
                "evidence_count": 0,
                "evidence_sample": "ERROR",
                "response_text": str(e),
                "has_evidence": False,
                "has_keyword": False,
                "passed": False,
                "target_doc_id": query_info["target_doc_id"],
                "expected_keywords": query_info["expected_keywords"],
            })

    # 결과 표 출력
    print("\n" + "=" * 140)
    print("테스트 결과 요약")
    print("=" * 140)

    print(f"\n{'#':<3} {'Query':<35} {'Time(ms)':<10} {'Evidence':<10} {'Evidence Sample':<50} {'Pass/Fail':<10}")
    print("-" * 140)

    for i, r in enumerate(results, 1):
        query_short = r["query"][:33] + ".." if len(r["query"]) > 35 else r["query"]
        sample_short = r["evidence_sample"][:48] + ".." if len(r["evidence_sample"]) > 50 else r["evidence_sample"]
        status = "PASS ✓" if r["passed"] else "FAIL ✗"

        print(f"{i:<3} {query_short:<35} {r['elapsed_ms']:<10} {r['evidence_count']:<10} {sample_short:<50} {status:<10}")

    # 통계
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    print("\n" + "=" * 140)
    print(f"통계: Total={total} | Pass={passed} | Fail={failed} | Pass Rate={pass_rate:.1f}%")
    print("=" * 140)

    # 실패 케이스 분석
    if failed > 0:
        print("\n실패 케이스 분석:")
        print("-" * 140)
        for i, r in enumerate(results, 1):
            if not r["passed"]:
                print(f"\n[실패 #{i}] {r['query']}")
                print(f"  - Target Doc: {r['target_doc_id']}")
                print(f"  - Expected Keywords: {', '.join(r['expected_keywords'])}")
                print(f"  - Evidence Count: {r['evidence_count']} (기대: ≥1)")
                print(f"  - Has Keyword: {r['has_keyword']} (기대: True)")
                print(f"  - Response Text: {r['response_text'][:200]}...")

                # 원인 가설
                if r['evidence_count'] == 0:
                    print(f"  → 원인 가설: 검색 결과 없음 (인덱스 미구축 또는 쿼리 불일치)")
                elif not r['has_keyword']:
                    print(f"  → 원인 가설: Evidence는 있으나 응답에 키워드 누락 (LLM 생성 문제)")

    # 개선 포인트
    print("\n" + "=" * 140)
    print("개선 필요 포인트:")
    print("-" * 140)

    avg_time = sum(r["elapsed_ms"] for r in results) / len(results) if results else 0
    avg_evidence = sum(r["evidence_count"] for r in results) / len(results) if results else 0

    print(f"1. 평균 응답 시간: {avg_time:.0f}ms → 목표: <500ms (필요 시 캐싱/인덱스 최적화)")
    print(f"2. 평균 Evidence 개수: {avg_evidence:.1f}건 → 목표: ≥3건 (검색 정확도 개선)")
    print(f"3. Pass Rate: {pass_rate:.1f}% → 목표: ≥80% (쿼리 확장 또는 재랭킹 강화)")

    print("\n" + "=" * 140)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
