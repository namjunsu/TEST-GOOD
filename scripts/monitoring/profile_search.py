#!/usr/bin/env python3
"""검색 성능 프로파일링

100회 반복 검색으로 병목 지점 탐지

사용법:
    python scripts/profile_search_performance.py "재난 관련 문서"
    python scripts/profile_search_performance.py "카메라 구매" --iterations 50
"""

import argparse
import cProfile
import pstats
import sys
import time
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.rag.retrievers.hybrid import HybridRetriever


def profile_search(query: str, iterations: int = 100, top_k: int = 5):
    """검색 성능 프로파일링

    Args:
        query: 검색 쿼리
        iterations: 반복 횟수
        top_k: 검색 결과 수
    """
    print("=" * 80)
    print("검색 성능 프로파일링")
    print("=" * 80)
    print(f"  - 쿼리: {query}")
    print(f"  - 반복 횟수: {iterations}")
    print(f"  - Top-K: {top_k}")
    print()

    # HybridRetriever 초기화
    print("HybridRetriever 초기화 중...")
    retriever = HybridRetriever()
    print("  ✅ 초기화 완료\n")

    # 워밍업 (1회)
    print("워밍업 중...")
    retriever.search(query, top_k=top_k)
    print("  ✅ 워밍업 완료\n")

    # 프로파일링 시작
    print(f"{iterations}회 반복 프로파일링 시작...")
    profiler = cProfile.Profile()
    profiler.enable()

    start_time = time.time()
    for i in range(iterations):
        retriever.search(query, top_k=top_k)
        if (i + 1) % 10 == 0:
            print(f"  진행: {i + 1}/{iterations}")

    elapsed = time.time() - start_time
    profiler.disable()

    print("\n✅ 프로파일링 완료")
    print(f"  - 총 시간: {elapsed:.2f}초")
    print(f"  - 평균 시간: {elapsed / iterations * 1000:.2f}ms/검색")
    print(f"  - QPS: {iterations / elapsed:.2f}")

    # 통계 분석
    print("\n" + "=" * 80)
    print("병목 함수 분석 (상위 20개)")
    print("=" * 80)

    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)

    # 시간별 정렬
    print("\n" + "=" * 80)
    print("시간 소모 함수 (상위 20개)")
    print("=" * 80)
    stats.sort_stats("tottime")
    stats.print_stats(20)


def main():
    parser = argparse.ArgumentParser(description="검색 성능 프로파일링")
    parser.add_argument("query", type=str, help="검색 쿼리")
    parser.add_argument("--iterations", type=int, default=100, help="반복 횟수 (기본: 100)")
    parser.add_argument("--top-k", type=int, default=5, help="검색 결과 수 (기본: 5)")

    args = parser.parse_args()

    profile_search(args.query, args.iterations, args.top_k)

    print("\n" + "=" * 80)
    print("프로파일링 완료")
    print("=" * 80)


if __name__ == "__main__":
    main()
