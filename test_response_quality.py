#!/usr/bin/env python3
"""
RAG 응답 품질 테스트
응답 생성이 정상적으로 개선되었는지 검증
"""

import time
from perfect_rag import PerfectRAG

def test_response_quality():
    print("="*60)
    print("🧪 RAG 응답 품질 테스트")
    print("="*60)
    
    # 시스템 초기화
    print("\n📦 시스템 로딩 중...")
    rag = PerfectRAG()
    print("✅ 시스템 로드 완료\n")
    
    # 테스트 쿼리 (사용자가 문제를 제기한 쿼리)
    test_query = "미러클랩 카메라 삼각대 기술검토서 알려줘"
    
    print(f"📝 테스트 쿼리: {test_query}")
    print("-"*60)
    
    # 응답 생성
    start = time.time()
    response = rag.answer(test_query, mode='document')
    elapsed = time.time() - start
    
    print(f"\n⏱️ 응답 시간: {elapsed:.1f}초")
    print(f"📏 응답 길이: {len(response):,} 글자")
    
    # 응답 품질 검사
    print("\n📊 응답 품질 분석:")
    print("-"*40)
    
    quality_checks = {
        '반복 없음': response.count(response[:100]) <= 1 if len(response) > 100 else True,
        '중국어 없음': not any(ord(c) >= 0x4E00 and ord(c) <= 0x9FFF for c in response),
        '이상한 텍스트 없음': all(w not in response for w in ['user', 'disappea', 'ac8c']),
        '한국어 포함': any(ord(c) >= 0xAC00 and ord(c) <= 0xD7AF for c in response),
        '적절한 길이': 100 < len(response) < 5000
    }
    
    all_passed = True
    for check, passed in quality_checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
        if not passed:
            all_passed = False
    
    # 응답 내용 출력
    print("\n📄 생성된 응답:")
    print("="*60)
    print(response[:1500] + "..." if len(response) > 1500 else response)
    print("="*60)
    
    # 결과 평가
    print("\n🎯 최종 평가:")
    if all_passed:
        print("  ✅ 응답 품질 테스트 통과! 정상적인 답변이 생성되었습니다.")
    else:
        print("  ⚠️ 일부 품질 검사 실패. 추가 개선이 필요합니다.")
    
    return all_passed

if __name__ == "__main__":
    success = test_response_quality()
    exit(0 if success else 1)
