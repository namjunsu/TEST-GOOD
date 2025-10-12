#!/usr/bin/env python3
"""
표 추출 통합 테스트
search_module의 표 추출 기능이 제대로 작동하는지 확인합니다.
"""

from modules.search_module import SearchModule
from pathlib import Path

def main():
    print("📊 표 추출 통합 테스트")
    print("="*80)

    # SearchModule 초기화
    search_module = SearchModule()

    # 테스트 문서 선택 (표가 포함된 것으로 확인된 문서)
    test_filename = "2025-08-26_뷰파인더_소모품_케이블_구매_건.pdf"

    print(f"\n🔍 테스트 문서: {test_filename}")
    print("-"*80)

    # 특정 문서 검색
    try:
        results = search_module.search_by_filename(test_filename, mode='detail')

        if results and len(results) > 0:
            result = results[0]

            print(f"✅ 문서 발견")
            print(f"  파일명: {result['filename']}")
            print(f"  내용 길이: {len(result.get('content', ''))}자")

            # 표 데이터 확인
            content = result.get('content', '')
            if '📊 **표 데이터**' in content:
                print("\n🎉 표 추출 성공!")

                # 표 부분만 추출
                table_parts = content.split('📊 **표 데이터**')
                print(f"  추출된 표 개수: {len(table_parts) - 1}개")

                # 첫 번째 표 출력
                if len(table_parts) > 1:
                    print("\n📋 첫 번째 표:")
                    print("-"*80)
                    first_table = table_parts[1].split('\n\n')[0]
                    print(first_table[:500])  # 처음 500자
            else:
                print("\n⚠️  표가 추출되지 않았습니다")
                print(f"\n내용 샘플 (처음 500자):")
                print(content[:500])

        else:
            print(f"❌ 문서를 찾을 수 없습니다: {test_filename}")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)

if __name__ == "__main__":
    main()
