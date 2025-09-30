#!/usr/bin/env python3
"""간단한 시스템 테스트"""
import time

print("=" * 60)
print("🚀 간단한 시스템 테스트")
print("=" * 60)

try:
    # 시스템 임포트
    print("\n1. 모듈 임포트 테스트...")
    from perfect_rag import PerfectRAG
    print("✅ PerfectRAG 임포트 성공")

    # 초기화
    print("\n2. 시스템 초기화...")
    start = time.time()
    rag = PerfectRAG()
    print(f"✅ 초기화 완료: {time.time() - start:.2f}초")

    # 간단한 질문
    print("\n3. 간단한 질문 테스트...")
    question = "카메라 구매"
    print(f"질문: {question}")

    start = time.time()
    response = rag.answer(question)
    elapsed = time.time() - start

    if response:
        print(f"✅ 응답 성공 ({elapsed:.2f}초)")
        print(f"응답 길이: {len(response)}자")
    else:
        print(f"⚠️ 빈 응답 ({elapsed:.2f}초)")

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")

except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()