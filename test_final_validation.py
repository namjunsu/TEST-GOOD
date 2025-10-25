#!/usr/bin/env python3
"""최종 검증 테스트"""

import sys
sys.path.insert(0, "/home/wnstn4647/AI-CHAT")

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from app.rag.pipeline import RAGPipeline

print("=" * 80)
print("최종 검증 테스트 (보강 패치 적용)")
print("=" * 80)

p = RAGPipeline()

test_queries = ["카메라 수리", "케이블 교체", "워크스테이션", "DVR", "팬 교체"]

results_summary = []

for q in test_queries:
    rs = p.retriever.search(q, top_k=5)
    lens = [len(r.get("snippet", "")) for r in rs[:3]]
    avg_len = sum(lens) / len(lens) if lens else 0

    print(f"\n질문: '{q}'")
    print(f"  결과 개수: {len(rs)}개")
    print(f"  snippet 길이 (상위 3개): {lens}")
    print(f"  snippet 평균: {avg_len:.0f}자")

    # backfill 여부 확인
    backfilled = sum(1 for r in rs if r.get("backfill", False))
    if backfilled > 0:
        print(f"  Backfill: {backfilled}개")

    results_summary.append({
        "query": q,
        "count": len(rs),
        "avg_snippet": avg_len,
        "backfilled": backfilled,
    })

print("\n" + "=" * 80)
print("검증 기준 확인")
print("=" * 80)

# 검증 기준
min_count_ok = all(r["count"] >= 3 for r in results_summary)
avg_snippet_ok = all(r["avg_snippet"] >= 200 for r in results_summary)

print(f"✅ 최소 결과 개수 (≥3): {'통과' if min_count_ok else '실패'}")
counts = [r['count'] for r in results_summary]
print(f"   - {counts}")

print(f"✅ snippet 평균 길이 (≥200자): {'통과' if avg_snippet_ok else '실패'}")
avgs = [int(r['avg_snippet']) for r in results_summary]
print(f"   - {avgs}")

if min_count_ok and avg_snippet_ok:
    print("\n🎉 모든 검증 기준 통과!")
else:
    print("\n⚠️ 일부 기준 미달")

print("=" * 80)
