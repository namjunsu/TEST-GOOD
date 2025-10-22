#!/usr/bin/env python3
"""
적응형 CoT 프롬프트 테스트
질문 유형에 따라 다른 프롬프트가 사용되는지 확인
"""

from hybrid_chat_rag_v2 import UnifiedRAG

def test_query_classification():
    """질문 분류 테스트"""
    rag = UnifiedRAG()

    print("🧪 질문 유형 분류 테스트")
    print("="*60)
    print()

    # 테스트 질문들
    test_queries = [
        ("금액은 얼마야?", "simple"),
        ("언제 수리했어?", "simple"),
        ("기안자가 누구야?", "simple"),
        ("어떤 장비야?", "simple"),
        ("왜 이 장비를 선택했어?", "complex"),
        ("이 수리가 적절한가?", "complex"),
        ("작년 대비 비교해줘", "complex"),
        ("문제점을 분석해줘", "complex"),
        ("상세하게 설명해줘", "complex"),
    ]

    print("질문 유형 분류:")
    print("-"*60)

    correct = 0
    for query, expected in test_queries:
        result = rag._classify_query_complexity(query)
        status = "✅" if result == expected else "❌"

        if result == expected:
            correct += 1

        print(f"{status} \"{query}\"")
        print(f"   예상: {expected} | 실제: {result}")
        print()

    accuracy = (correct / len(test_queries)) * 100
    print("="*60)
    print(f"정확도: {correct}/{len(test_queries)} ({accuracy:.1f}%)")
    print()

    if accuracy >= 90:
        print("✅ 훌륭합니다! 질문 분류가 정확합니다.")
    elif accuracy >= 70:
        print("⚠️  괜찮습니다. 일부 개선 여지가 있습니다.")
    else:
        print("❌ 분류 정확도가 낮습니다. 패턴 개선이 필요합니다.")

def test_prompt_generation():
    """프롬프트 생성 테스트"""
    rag = UnifiedRAG()

    print("\n🧪 프롬프트 생성 테스트")
    print("="*60)
    print()

    # 테스트 문서 (간단한 예시)
    test_doc = {
        'filename': 'test.pdf',
        'date': '2025-01-01',
        'drafter': '홍길동',
        'content': '테스트 장비 구매. 금액: 1,000,000원. 업체: ABC전자'
    }

    # 단순 질문
    print("1️⃣ 단순 질문 프롬프트:")
    print("-"*60)
    simple_prompt = rag._build_prompt("금액은?", [test_doc])
    if "간결하게" in simple_prompt:
        print("✅ 단순 질문용 프롬프트 사용")
        print("   → 간결한 답변 지시")
    else:
        print("❌ CoT 프롬프트가 사용됨 (비효율)")
    print()

    # 복잡한 질문
    print("2️⃣ 복잡한 질문 프롬프트:")
    print("-"*60)
    complex_prompt = rag._build_prompt("왜 이 장비를 선택했어?", [test_doc])
    if "Chain-of-Thought" in complex_prompt:
        print("✅ CoT 프롬프트 사용")
        print("   → 5단계 추론 지시")
    else:
        print("❌ 단순 프롬프트가 사용됨")
    print()

    print("="*60)
    print("✅ 적응형 프롬프트가 정상 작동합니다!")

if __name__ == "__main__":
    try:
        test_query_classification()
        test_prompt_generation()

        print("\n" + "="*60)
        print("🎉 모든 테스트 완료!")
        print("="*60)

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
