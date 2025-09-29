#!/usr/bin/env python3
"""
메타데이터 추출 기능 통합 테스트
2025-09-29 작성
"""

import sys
import time
from pathlib import Path
from perfect_rag import PerfectRAG

def test_metadata_integration():
    """메타데이터 추출 기능 통합 테스트"""

    print("=" * 60)
    print("🧪 메타데이터 추출 기능 통합 테스트")
    print("=" * 60)

    # PerfectRAG 인스턴스 생성
    print("\n1️⃣ PerfectRAG 초기화 중...")
    rag = PerfectRAG()

    # 메타데이터 추출기 확인
    if hasattr(rag, 'metadata_extractor') and rag.metadata_extractor:
        print("✅ MetadataExtractor가 정상적으로 로드되었습니다.")
    else:
        print("❌ MetadataExtractor 로드 실패!")
        return False

    # 테스트 쿼리들
    test_queries = [
        "카메라 구매",
        "2024년 조명",
        "DVR 관련 문서"
    ]

    print("\n2️⃣ 검색 테스트 시작...")
    print("-" * 40)

    for query in test_queries:
        print(f"\n🔍 검색: '{query}'")

        try:
            # 내부 검색 메서드 호출
            start = time.time()
            results = rag._search_by_content(query)
            elapsed = time.time() - start

            print(f"  ⏱️ 검색 시간: {elapsed:.2f}초")
            print(f"  📊 결과: {len(results)}개 문서")

            # 상위 3개 결과 출력
            for i, doc in enumerate(results[:3], 1):
                print(f"\n  [{i}] {doc['filename']}")

                # 메타데이터 확인
                has_metadata = False

                if 'extracted_date' in doc:
                    print(f"      📅 날짜: {doc['extracted_date']}")
                    has_metadata = True

                if 'extracted_amount' in doc:
                    print(f"      💰 금액: {doc['extracted_amount']:,}원")
                    has_metadata = True

                if 'extracted_dept' in doc:
                    print(f"      🏢 부서: {doc['extracted_dept']}")
                    has_metadata = True

                if 'extracted_type' in doc:
                    print(f"      📑 유형: {doc['extracted_type']}")
                    has_metadata = True

                if not has_metadata:
                    print(f"      ⚠️ 메타데이터 없음")

        except Exception as e:
            print(f"  ❌ 오류: {e}")

    print("\n" + "=" * 60)
    print("3️⃣ 전체 answer 메서드 테스트")
    print("-" * 40)

    # 실제 answer 메서드 테스트
    test_query = "2024년 카메라 구매 문서"
    print(f"\n질문: {test_query}")

    try:
        answer = rag.answer(test_query)
        print("\n응답 미리보기:")
        print("-" * 40)
        # 처음 500자만 출력
        preview = answer[:500] if len(answer) > 500 else answer
        print(preview)
        if len(answer) > 500:
            print("... (생략)")

        # 메타데이터 정보가 포함되었는지 확인
        if "💰" in answer:
            print("\n✅ 금액 정보가 응답에 포함됨!")
        if "📅" in answer or "2024" in answer:
            print("✅ 날짜 정보가 응답에 포함됨!")

    except Exception as e:
        print(f"❌ answer 메서드 오류: {e}")

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = test_metadata_integration()
    sys.exit(0 if success else 1)