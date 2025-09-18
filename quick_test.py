#!/usr/bin/env python3
"""
빠른 라우팅 테스트
"""

import sys
import os
from pathlib import Path

# 디버그 출력 캡처를 위한 설정
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def quick_test():
    """라우팅 테스트"""
    
    print("=" * 70)
    print("라우팅 테스트 시작")
    print("=" * 70)
    
    # RAG 시스템 초기화 (디버그 모드)
    rag = PerfectRAG()
    
    # 테스트 쿼리
    query = "중계차 장비 목록"
    
    print(f"\n테스트 쿼리: {query}")
    print("-" * 70)
    
    # 검색 의도 분류
    intent = rag._classify_search_intent(query)
    print(f"검색 의도: {intent}")
    
    if intent == 'asset':
        print("✅ asset 모드로 올바르게 분류됨")
    else:
        print(f"❌ 잘못된 분류: {intent}")
    
    print("\n디버그 메시지를 확인하기 위해 실제 쿼리 실행...")
    print("-" * 70)
    
    # 실제 쿼리 실행 (처음 부분만)
    # answer 메서드를 직접 호출하여 디버그 메시지 확인
    try:
        # 내부 메서드 직접 호출
        result = rag._answer_internal(query, mode='asset')
        
        # 결과 첫 500자만 출력
        print("\n결과 일부:")
        print(result[:500] if result else "결과 없음")
        
        # 결과 분석
        if "📊" in result and "중계차" in result:
            print("\n✅ 중계차 장비 현황이 정상적으로 표시됨")
        if "💰" in result or "금액" in result:
            print("✅ 금액 정보 포함")
        if "📅" in result or "구입일" in result:
            print("✅ 구입일 정보 포함")
        if "👤" in result or "담당자" in result:
            print("✅ 담당자 정보 포함")
            
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    quick_test()