#!/usr/bin/env python3
"""
정리된 perfect_rag.py 테스트
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_cleaned_rag():
    print("\n" + "="*60)
    print("   정리된 Perfect RAG 시스템 테스트")
    print("="*60)
    
    # RAG 초기화
    print("\n1. 시스템 초기화...")
    try:
        rag = PerfectRAG(preload_llm=False)
        print("✅ 초기화 성공")
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return
    
    # 기본 정보 출력
    print(f"\n2. 시스템 정보:")
    print(f"   - PDF 파일: {len(rag.pdf_files)}개")
    print(f"   - TXT 파일: {len(rag.txt_files)}개")
    print(f"   - 메타데이터 DB: {'활성화' if rag.metadata_db else '비활성화'}")
    
    # 테스트 쿼리
    test_queries = [
        "2020년 구매 문서",
        "김 기안자 문서",
        "카메라 수리 관련 문서"
    ]
    
    print(f"\n3. 문서 검색 테스트:")
    print("-" * 60)
    
    for query in test_queries:
        print(f"\n쿼리: {query}")
        try:
            result = rag.search(query)
            if result:
                # 결과 첫 200자만 출력
                if len(result) > 200:
                    print(f"결과: {result[:200]}...")
                else:
                    print(f"결과: {result}")
            else:
                print("결과 없음")
        except Exception as e:
            print(f"❌ 검색 오류: {e}")
    
    print("\n" + "="*60)
    print("✅ 테스트 완료!")
    print("="*60)

if __name__ == "__main__":
    test_cleaned_rag()