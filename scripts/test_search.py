#!/usr/bin/env python3
"""
검색 테스트 스크립트
OCR로 처리된 문서가 검색되는지 확인
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.embeddings import VectorStore

def main():
    print("=" * 80)
    print("벡터 검색 테스트: '마스터 싱크제너레이터'")
    print("=" * 80)

    vector_store = VectorStore(index_path="data/vector_index")

    query = "마스터 싱크제너레이터"
    results = vector_store.search(query, top_k=5)

    print(f"\n검색 쿼리: {query}")
    print(f"결과 수: {len(results)}\n")

    for i, result in enumerate(results, 1):
        print(f"{i}. {result['doc_id']}")
        print(f"   유사도: {result['score']:.4f}")
        print(f"   텍스트: {result['text'][:100]}...")
        print()

if __name__ == "__main__":
    main()
