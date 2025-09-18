#!/usr/bin/env python3
"""
장비 검색 테스트 스크립트
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_equipment_search():
    """중계차 장비 목록 검색 테스트"""
    
    print("=" * 70)
    print("장비 검색 테스트 시작")
    print("=" * 70)
    
    # RAG 시스템 초기화
    rag = PerfectRAG()
    
    # 테스트 쿼리들
    test_queries = [
        "중계차 장비 목록",
        "중계차 장비 현황",
        "News VAN 장비 목록",
    ]
    
    for query in test_queries:
        print(f"\n\n{'='*70}")
        print(f"테스트 쿼리: {query}")
        print("="*70)
        
        # 검색 수행
        result = rag.answer_with_logging(query, mode='asset')
        
        # 결과 출력
        print("\n📊 검색 결과:")
        print("-" * 70)
        print(result[:2000])  # 처음 2000자만 출력
        
        # 결과 분석
        print("\n📈 결과 분석:")
        print("-" * 70)
        
        # 상세 정보 포함 여부 확인
        has_price = "💰" in result or "금액" in result or "원" in result
        has_date = "📅" in result or "구입일" in result
        has_manager = "👤" in result or "담당자" in result
        has_serial = "🔤" in result or "시리얼" in result
        has_model = "📌" in result or "모델" in result
        
        print(f"✅ 가격 정보 포함: {'예' if has_price else '아니오'}")
        print(f"✅ 구입일 정보 포함: {'예' if has_date else '아니오'}")
        print(f"✅ 담당자 정보 포함: {'예' if has_manager else '아니오'}")
        print(f"✅ 시리얼 정보 포함: {'예' if has_serial else '아니오'}")
        print(f"✅ 모델 정보 포함: {'예' if has_model else '아니오'}")
        
        # 카테고리 문제 확인
        wrong_categories = ["64GB 장비", "AIR 장비", "기타 장비"]
        has_wrong_categories = any(cat in result for cat in wrong_categories)
        
        if has_wrong_categories:
            print(f"⚠️ 잘못된 카테고리 발견!")
        else:
            print(f"✅ 카테고리 정상")

if __name__ == "__main__":
    test_equipment_search()