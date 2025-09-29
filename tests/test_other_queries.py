#!/usr/bin/env python3
"""
DVR 외 다른 검색어 테스트
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_various_queries():
    print("="*50)
    print("다양한 검색어 테스트")
    print("="*50)

    rag = PerfectRAG()

    test_queries = [
        "중계차 관련 문서",
        "카메라 수리 문서",
        "2020년 구매 문서",
        "조명 관련 문서",
        "소모품 신청서"
    ]

    for query in test_queries:
        print(f"\n질문: {query}")
        print("-"*50)

        # 내용 기반 검색 테스트
        results = rag._search_by_content(query)

        print(f"✅ {len(results)}개 문서 발견\n")

        for i, result in enumerate(results[:3], 1):
            print(f"{i}. {result['filename']}")
            print(f"   점수: {result['score']}")
            print()

if __name__ == "__main__":
    test_various_queries()