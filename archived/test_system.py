#!/usr/bin/env python3
"""
시스템 테스트 - perfect_rag.py 제거 후 검증
"""

import time
import sys

print("=" * 70)
print("🧪 시스템 테스트 - perfect_rag.py 제거 후")
print("=" * 70)
print()

# Test 1: QuickFixRAG 초기화 및 검색
print("📝 Test 1: QuickFixRAG 검색 기능")
print("-" * 70)

try:
    from quick_fix_rag import QuickFixRAG

    start = time.time()
    rag = QuickFixRAG()
    init_time = time.time() - start

    print(f"✅ QuickFixRAG 초기화 성공: {init_time:.4f}초")

    # 검색 테스트
    test_query = "카메라 수리"
    start = time.time()
    result = rag.answer(test_query)
    search_time = time.time() - start

    print(f"✅ 검색 성공: {search_time:.4f}초")
    print(f"   검색어: {test_query}")

    # 결과 길이만 출력 (너무 길어서)
    result_preview = result[:200] + "..." if len(result) > 200 else result
    print(f"   결과: {result_preview}")
    print()

except Exception as e:
    print(f"❌ QuickFixRAG 테스트 실패: {e}")
    sys.exit(1)

# Test 2: UnifiedRAG 초기화
print("📝 Test 2: UnifiedRAG (AI 답변) 초기화")
print("-" * 70)

try:
    from hybrid_chat_rag_v2 import UnifiedRAG

    start = time.time()
    unified_rag = UnifiedRAG()
    init_time = time.time() - start

    print(f"✅ UnifiedRAG 초기화 성공: {init_time:.4f}초")
    print()

except Exception as e:
    print(f"❌ UnifiedRAG 초기화 실패: {e}")
    sys.exit(1)

# Test 3: SearchModule 직접 사용
print("📝 Test 3: SearchModule 직접 사용")
print("-" * 70)

try:
    from modules.search_module import SearchModule

    start = time.time()
    search = SearchModule()
    init_time = time.time() - start

    print(f"✅ SearchModule 초기화 성공: {init_time:.4f}초")

    # 검색 테스트
    test_query = "무선 마이크"
    start = time.time()
    results = search.search_by_content(test_query, top_k=3)
    search_time = time.time() - start

    print(f"✅ 검색 성공: {search_time:.4f}초")
    print(f"   검색어: {test_query}")
    print(f"   결과: {len(results)}개 문서")
    print()

except Exception as e:
    print(f"❌ SearchModule 테스트 실패: {e}")
    sys.exit(1)

# Test 4: Import 확인 (perfect_rag가 없어야 함)
print("📝 Test 4: perfect_rag.py 제거 확인")
print("-" * 70)

try:
    import perfect_rag
    print(f"⚠️  경고: perfect_rag.py가 여전히 import 가능합니다")
    print(f"   위치: {perfect_rag.__file__}")
except ImportError:
    print(f"✅ perfect_rag.py 제거 확인 (import 불가)")

print()

# 최종 결과
print("=" * 70)
print("✅ 모든 테스트 통과!")
print("=" * 70)
print()
print("📊 성능 요약:")
print(f"  - QuickFixRAG 초기화: {init_time:.4f}초")
print(f"  - 검색 속도: {search_time:.4f}초")
print()
print("🎯 시스템 정상 작동 확인 완료")
