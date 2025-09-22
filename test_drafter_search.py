#!/usr/bin/env python3
"""
기안자 검색 테스트 스크립트
"""

from perfect_rag import PerfectRAG
import time

def test_drafter_search():
    """기안자 검색 기능 테스트"""

    print("🔧 RAG 시스템 초기화 중...")
    rag = PerfectRAG(preload_llm=False)

    # metadata_db 속성 확인
    if hasattr(rag, 'metadata_db'):
        print(f"✅ metadata_db 속성 존재: {rag.metadata_db is not None}")
    else:
        print("❌ metadata_db 속성이 없습니다!")
        return

    # 테스트 쿼리들
    test_queries = [
        "김XX 기안자가 작성한 문서",
        "박XX가 기안한 문서 찾아줘",
        "이XX 기안자 문서 목록"
    ]

    for query in test_queries:
        print(f"\n📝 테스트 쿼리: {query}")
        print("-" * 50)

        try:
            start_time = time.time()
            response = rag.answer(query, mode='document')
            elapsed = time.time() - start_time

            # 응답 길이 제한
            if len(response) > 500:
                response_preview = response[:500] + "..."
            else:
                response_preview = response

            print(f"✅ 응답 ({elapsed:.2f}초):")
            print(response_preview)

        except AttributeError as e:
            print(f"❌ AttributeError 발생: {e}")
        except Exception as e:
            print(f"❌ 오류 발생: {e}")

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")

if __name__ == "__main__":
    test_drafter_search()