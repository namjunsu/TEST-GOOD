#!/usr/bin/env python3
"""
RAG 시스템 실제 답변 품질 테스트
"""

from perfect_rag import PerfectRAG
import time

def test_answer_quality():
    """실제 질의응답 테스트"""
    print("🔍 RAG 시스템 답변 품질 테스트")
    print("="*60)
    
    # RAG 시스템 초기화
    print("시스템 초기화 중...")
    rag = PerfectRAG()
    
    # 테스트 질문들
    test_queries = [
        # 장비 관련 질문
        {
            "query": "중계차 장비 목록을 알려줘",
            "mode": "asset",
            "description": "장비 자산 검색"
        },
        {
            "query": "HD 카메라 구매 내역",
            "mode": "asset", 
            "description": "특정 장비 검색"
        },
        # 문서 관련 질문
        {
            "query": "구매업무 절차는 어떻게 되나요?",
            "mode": "document",
            "description": "업무 절차 문서 검색"
        },
        {
            "query": "2024년에 구매한 장비 중 가장 비싼 것은?",
            "mode": "document",
            "description": "복잡한 질문"
        }
    ]
    
    # 각 질문 테스트
    for i, test in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"테스트 {i}: {test['description']}")
        print(f"질문: {test['query']}")
        print(f"모드: {test['mode']}")
        print("-"*60)
        
        try:
            start_time = time.time()
            
            # RAG 시스템 호출
            response = rag.answer(
                test['query'], 
                mode=test['mode']
            )
            
            elapsed = time.time() - start_time
            
            # 응답 출력
            print("📝 응답:")
            if isinstance(response, dict):
                answer = response.get('answer', response)
                if isinstance(answer, str):
                    # 답변이 너무 길면 처음 500자만 출력
                    if len(answer) > 500:
                        print(answer[:500] + "...\n[답변 일부 생략]")
                    else:
                        print(answer)
                else:
                    print(str(answer)[:500])
            else:
                print(str(response)[:500])
            
            print(f"\n⏱️ 응답 시간: {elapsed:.2f}초")
            print("✅ 답변 생성 성공")
            
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
    
    print(f"\n{'='*60}")
    print("테스트 완료!")

if __name__ == "__main__":
    test_answer_quality()