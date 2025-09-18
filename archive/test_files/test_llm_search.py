#!/usr/bin/env python3
"""
LLM 기반 장비 검색 테스트
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_llm_search():
    """LLM 검색 테스트"""
    
    print("=" * 70)
    print("LLM 기반 장비 검색 테스트")
    print("=" * 70)
    
    # RAG 시스템 초기화
    rag = PerfectRAG()
    
    # 테스트 질문들 (LLM이 필요한 복잡한 질문)
    test_queries = [
        "가장 비싼 장비는 뭐야?",
        "2020년에 구입한 장비 중 주요 장비들 알려줘",
        "소니 장비 중에서 카메라 관련 장비들 정리해줘"
    ]
    
    for query in test_queries:
        print(f"\n테스트 쿼리: {query}")
        print("-" * 70)
        
        # 실제 쿼리 실행
        result = rag._answer_internal(query, mode='asset')
        
        # 결과 출력 (처음 1000자)
        print("결과:")
        print(result[:1000] if result else "결과 없음")
        print("-" * 70)
        
        # LLM 사용 여부 확인
        if "AI 분석 결과" in result:
            print("✅ LLM이 사용되었습니다")
        else:
            print("⚠️ LLM이 사용되지 않았습니다")

if __name__ == "__main__":
    test_llm_search()