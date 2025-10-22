#!/usr/bin/env python3
"""
AI 답변 생성 테스트 (queso/Llama-3-Gukbap-8B)
"""

import time

print("=" * 70)
print("🧪 AI 답변 생성 테스트")
print("=" * 70)
print()

# Test: UnifiedRAG로 AI 답변 생성
print("📝 Test: AI 답변 생성 (Llama-3-Gukbap-8B)")
print("-" * 70)

try:
    from hybrid_chat_rag_v2 import UnifiedRAG

    rag = UnifiedRAG()
    print(f"✅ UnifiedRAG 초기화 완료")
    print()

    # 테스트 질문
    test_query = "2025년 카메라 수리 관련 문서는?"

    print(f"질문: {test_query}")
    print()
    print("⏳ AI 답변 생성 중... (30-60초 소요)")

    start = time.time()
    answer = rag.answer(test_query)
    elapsed = time.time() - start

    print()
    print("=" * 70)
    print("📄 AI 답변:")
    print("=" * 70)
    print(answer)
    print()
    print("=" * 70)
    print(f"⏱️  응답 시간: {elapsed:.1f}초")
    print("=" * 70)

except Exception as e:
    print(f"❌ 테스트 실패: {e}")
    import traceback
    traceback.print_exc()
