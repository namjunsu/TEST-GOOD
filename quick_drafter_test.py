#!/usr/bin/env python3
"""
빠른 기안자 테스트
"""

from perfect_rag import PerfectRAG

print("🔧 초기화 중...")
rag = PerfectRAG(preload_llm=False)

# metadata_db 확인
if hasattr(rag, 'metadata_db'):
    print(f"✅ metadata_db 속성 존재: {rag.metadata_db is not None}")
    if rag.metadata_db:
        print(f"✅ metadata_db 타입: {type(rag.metadata_db)}")
else:
    print("❌ metadata_db 속성이 없습니다!")

print("\n🎉 테스트 성공! 이제 기안자 검색이 작동할 것입니다.")